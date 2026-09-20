# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## What this is

**GridShift** places deferrable compute jobs (batch training, ETL, rendering) into
hours of the PJM grid that cost less carbon *and* water, and explains the
tradeoff in plain English. The finding behind it (from `pjm-water-carbon`,
vendored into `data/`): in PJM, carbon-optimal and water-optimal hours
**disagree** on an average-intensity basis, because nuclear is low-carbon but
withdraws a lot of water. On a marginal-empirical basis they largely agree.
Which of these is true for a user depends on the accounting basis. The product
exists to make that choice visible, not to hide it.

Layout:

| path | role |
|---|---|
| `app.py` | orchestration: classify → place → explain → verify |
| `gridshift/signals.py` | **vendored** read-only loader for `data/profile_*.csv` |
| `gridshift/classify.py` | Nemotron job #1 (deferability) |
| `gridshift/explain.py` | Nemotron job #2 (tradeoff narration) + `PlacementRecord` |
| `gridshift/verify.py` | deterministic guards on all model output |
| `data/` | vendored profiles + `build_profiles.py` (one-off, never run at runtime) |
| `eval/` | classification and explanation eval sets |
| `results/` | eval outputs |

## Hard rules

1. **Nemotron never states a number Python didn't compute.** No intensities,
   percentages, hours, gallons, kilograms or counts originate in model text.
   - classify: the model returns a *verbatim phrase* (`window_phrase`); Python
     parses it into `window_h`. `rationale` may not contain digits.
   - explain: the model may only print strings that appear in
     `PlacementRecord.display`, copied exactly. It does no rounding, unit
     conversion, differencing or ranking of its own.
   - `gridshift/verify.py` enforces this mechanically. On any violation the output
     is discarded and `explain.fallback()` (a pure-Python template) is shown.
2. **No savings figure appears without its accounting basis named.** Every
   sentence (in model output, UI, README, eval reports and commit messages)
   that states a savings or delta figure names its basis: `average` or
   `marginal-empirical`. A figure on one basis is never compared to, or
   substituted for, a figure on the other.
3. **Water is two metrics, never one.** Withdrawal and consumption are always
   reported separately. There is no combined "water" number.
4. **No recomputation at runtime.** `signals.py` reads CSVs only. No EIA fetch,
   no EIA-860 parsing, no regressions. To change the data, re-run
   `data/build_profiles.py` against the upstream repo at a pinned commit and
   update the commit hash in the headers.
5. **Do not modify `~/pjm-water-carbon`.** It is the upstream source of truth.
6. WHEN COMMITING, DO NOT INCLUDE THE CLAUDE WATERMARK IN THE COMMIT NAME FOR
  THE SAKE OF KEEPING THE COMMITS SHORT

## Nemotron job #1: classify

**Input:** one plain-English job description from the user.
**Task:** is this job deferable, is it interruptible, and which words state its
time flexibility?

```json
{
  "label": "deferable | not_deferable | unclear",
  "interruptible": true,
  "window_phrase": "before the 9am standup",
  "rationale": "Nightly retraining with a morning deadline can wait for cleaner hours."
}
```

| field | type | rule |
|---|---|---|
| `label` | enum | `unclear` when the text doesn't say; never guess `deferable` |
| `interruptible` | bool \| null | null when not stated |
| `window_phrase` | string \| null | **verbatim substring** of the input, or null |
| `rationale` | string | one sentence, **no digits** |

Python then derives `window_h` from `window_phrase`. If that fails, the job is
treated as not deferable.

## Nemotron job #2: explain

**Input:** one `PlacementRecord` (see `gridshift/explain.py`), built entirely by
Python: basis, objective, arrival and placed slot, shift, window, energy,
per-metric `{units, baseline, placed, delta_pct}` for carbon / consumption /
withdrawal, the computed `tradeoff` (`aligned | conflict | neutral`), the
`source` commit, and a `display` map of dotted field path → the exact string
the model may print.

**Task:** explain what moving the job bought and what it cost, using ONLY
fields from the record. No outside facts about fuels, cooling, PJM or weather
unless they are a field in the record.

```json
{
  "headline": "Moving this job to 6pm saves water but costs carbon (average basis).",
  "explanation": "On the average basis, ...",
  "fields_used": ["placed.hour", "withdrawal.delta_pct", "carbon.delta_pct", "basis"]
}
```

| field | type | rule |
|---|---|---|
| `headline` | string | one sentence; every number is a `display` value; names the basis if it states a figure |
| `explanation` | string | two to four sentences; same rules |
| `fields_used` | string[] | dotted paths; each must exist in the record |

(The numbers in the example are schematic. At runtime every figure is a
`display` string.)

## Conventions

- Bases are spelled `average` and `marginal_empirical` in code and
  `average` / `marginal-empirical` in prose.
- Hours are EIA-930 hour-ending, 1–24, PJM local time.
- Vendored code carries a header naming `pjm-water-carbon` and the commit hash.
- Savings sign: positive = less than run-on-arrival; negative = worse.

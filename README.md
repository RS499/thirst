# thirst

**Schedule your compute when the grid is less thirsty, and see what that costs
in carbon.**

Power plants need water for cooling. On the PJM grid (13 eastern states and
DC), I found the lowest-carbon hour and the lowest-water hour disagree on 360 of
365 days. thirst reads a compute job in plain English, works out how long it
can wait, places it in the best hour for carbon or water, and shows what that
choice trades away.

## Why this matters

Carbon-aware schedulers are real and deployed, shifting batch work into
cleaner hours today. On this grid their
advice quietly makes water worse. Nobody checks, because nobody measures both.

## The finding

Source: [`pjm-water-carbon`](../pjm-water-carbon) @ `28aecf4`: EIA-930 hourly
generation × EIA-860 plant cooling types, 2025-09-17 → 2026-09-16, 8,760 hours.

**Water withdrawal** is water taken from a river and mostly returned;
**consumption** is water evaporated and gone. They are always reported
separately. The **average basis** counts what was in the average kilowatt-hour
you drew; the **marginal-empirical basis** counts which plants actually turned
up when you added load. Figures are average basis unless marked.

- **Clean and low-water are different times of day.** On the year-averaged
  profile, carbon bottoms out at hour-ending 13 and withdrawal at hour-ending
  19, 6 hours apart.
- **Day by day, they almost never agree:** the two hours differ on **360 of
  365 days (98.6 %)**, by 6.7 h on average. The **independence null** (how
  often two unrelated hours would differ by chance alone) is 97.1 %: they line
  up no more than chance.
- **Worse than unrelated, they are opposed.** Across the year's hours, carbon
  and withdrawal are negatively correlated (r = −0.465). Picking the cleanest
  hour tends to pick a thirstier one.
- **Why: clean nuclear is thirsty.** **Once-through cooling** pulls river water
  straight through a plant and returns it, rather than recirculating it.
  Once-through nuclear delivers **13.3 % of PJM's generation** at about
  12 gCO₂/kWh but about 44,350 gal/MWh withdrawn. An hour that is clean
  *because* of nuclear is also water-heavy.
- **It's specific to this grid.** Of eight **balancing authorities** (the
  operators running each region's grid), five have usable cooling data, and
  only PJM shows the conflict. In MISO, BPAT, ERCO and SOCO the minima coincide
  far more often than chance: 25–70 % of days differ against an 85–91 %
  independence null. ISNE, NYIS and CISO fail the coverage check and are not
  counted. Across the five, once-through nuclear's share of generation
  explains the withdrawal correlation (R² = 0.82, p = 0.034, n = 5).
- **How you count flips the answer.** In a scheduling simulation,
  carbon-optimized scheduling *increases* withdrawal by 0.29 % to 1.87 % across
  2–24 h of slack (average basis). It saves 3.05 % carbon and 6.37 % withdrawal
  at 24 h of slack on the marginal-empirical basis, where nuclear
  never answers added load. So thirst never shows a figure without its basis.

## Where Nemotron sits

Nemotron (`nvidia/nemotron-3-super-120b-a12b`, NVIDIA's hosted API) does two
jobs; Python does everything else.

**(a) Classify: plain-English job → structured deferability** (`thirst/classify.py`).
A job is **deferable** when its text states a deadline that resolves to a
number of hours. The model returns a label and a *verbatim quote* ("before
the 9am standup"), never an hour count. Python confirms the quote is in the
input; `parse_window_hours()` resolves it against anchors elsewhere in the text
("my flight is Thursday at 6am") and does the arithmetic.

**(b) Explain: narrate the tradeoff from a `PlacementRecord`** (`thirst/explain.py`).
Python builds the record, with every figure pre-formatted as a display string.
Nemotron writes a headline and 2–4 sentences from those fields only.

**The rule: Nemotron never emits a number Python didn't compute.** This is
enforced mechanically by `thirst/verify.py`, not by prompt instructions: every
number must match a display string, sign included; every sentence with a figure
must name its basis; no outside facts or invented fields. Any violation swaps
in `explain.fallback()`, a deterministic Python template. The model can make an
explanation worse, but it cannot put a wrong number in front of the user.

## Evidence

Development set: `eval/labeled.jsonl`, 60 hand-written rows. Per-run results in
`results/progress.csv`; per-row detail in `results/*_eval.json`.

| what | result | baseline / note |
|---|---|---|
| Classify accuracy (60 rows) | **0.983** (59/60) | majority class ("deferable"): 0.550. Up from 0.917 by a **label-definition change, not a model improvement**: L21/L26/L30 relabeled, prompt and code unchanged (see FAILURES.md #7) |
| Classify accuracy before that relabel | 0.917 (55/60) | majority class: 0.500 |
| Classify accuracy, excluding one HTTP 429 | 0.932 (55/59) | the 429 was scored as "unclear", i.e. wrong |
| Classify, ambiguous rows | 0.000 → **0.933** | before → after the label-definition fix (see FAILURES.md) |
| Classify, no-deadline rows | 0.400 → **1.000** | before → after the same fix |
| Window MAE where both parsed | **0.00 h** in every run | optimistic: see Limitations |
| Explain numeric fidelity | **0.90** (18/20) | both failures were sign mismatches, caught by `verify()` |
| Fallback template passes `verify()` | **4032/4032** | 4 seasons × 24 arrival hours × 7 windows × 3 objectives × 2 bases, offline |
| Holdout | sealed | 30 rows, sha256 in `results/HOLDOUT_HASH.txt`; to be opened exactly once, on Sunday. Score: TODO |

For scale: always answering "unclear" scores 1.000 on ambiguous rows and 0.000
on standard and unusual rows. The classifier is the only thing that scores well
across all four categories.

## Limitations

- **Window MAE is optimistic.** The deadline parser was built against this same
  development set. Given the gold quotes it resolves 40/40 exactly. The 0.00 h
  is measured only where both the model's quote and the parse succeeded. The
  holdout is the honest test.
- **`verify()` checks that a number exists, not that it is on the right
  metric.** It confirms every number appears in `display` with the right sign.
  It does not catch the model attaching the carbon delta to the withdrawal
  sentence.
- **Free-tier rate limits.** One HTTP 429 in the final classify run, despite
  sequential calls, a 1 s pause and 5 SDK retries with backoff.
- **The regional regression is n = 5.** R² = 0.82 with p = 0.034 on five points
  is suggestive, not established.
- **Savings figures come from a synthetic workload trace.** Upstream's savings
  percentages (both bases) come from 5,000 synthetic deferrable jobs. The sign
  and ordering of effects are robust, but the magnitudes inherit the trace's
  shape.

## Run

```bash
pip install -r requirements.txt
echo 'NVIDIA_API_KEY=nvapi-...' > .env      # gitignored
python3 -m streamlit run app.py              # NOT `streamlit run app.py`
```

Terminal path: `python3 run.py "It's 10pm. Fine-tuning overnight, need it before the 9am standup"`.
Evals: `python3 eval/run_eval.py` (classify) and `python3 eval/explain_eval.py` (explain).

## Team

| name | email |
|---|---|
| TODO | TODO |

## Prior work disclosure

The PJM grid analysis (`pjm-water-carbon`) is separate prior research. This
repo uses it only as a data source, vendored at commit `28aecf4` as
pre-computed hourly profiles in `data/`, with no recomputation at runtime.
Everything in this repository was built during SteelHacks XIII: the classifier,
deadline parser, placer, explainer, verifier, evals and app.

## License

MIT. See [LICENSE](LICENSE).

# GridShift

**Schedule your compute when the grid is less thirsty, and see what that costs
in carbon.**

Power plants need water for cooling. On the PJM grid (13 eastern states and
DC), I found the lowest-carbon hour and the lowest-water hour disagree on 360 of
365 days. GridShift reads a compute job in plain English, works out how long it
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
  never answers added load. So GridShift never shows a figure without its basis.

## Where Nemotron sits

Nemotron (`nvidia/nemotron-3-super-120b-a12b`, NVIDIA's hosted API) does two
jobs; Python does everything else.

**(a) Classify: plain-English job → structured deferability** (`gridshift/classify.py`).
A job is **deferable** when its text states a deadline that resolves to a
number of hours. The model returns a label and a *verbatim quote* ("before
the 9am standup"), never an hour count. Python confirms the quote is in the
input; `parse_window_hours()` resolves it against anchors elsewhere in the text
("my flight is Thursday at 6am") and does the arithmetic.

**(b) Explain: narrate the tradeoff from a `PlacementRecord`** (`gridshift/explain.py`).
Python builds the record, with every figure pre-formatted as a display string.
Nemotron writes a headline and 2–4 sentences from those fields only.

**The rule: Nemotron never emits a number Python didn't compute.** This is
enforced mechanically by `gridshift/verify.py`, not by prompt instructions: every
number must match a display string, sign included; every sentence with a figure
must name its basis; no outside facts or invented fields. Any violation swaps
in `explain.fallback()`, a deterministic Python template. The model can make an
explanation worse, but it cannot put a wrong number in front of the user.

## How it places

Placement is pure Python over the vendored profiles; no model call is involved.

- **One block (the default).** The job runs as one unbroken stretch, and the
  placer picks the start hour. It prices that start hour, not the whole run, so
  a long job is priced by its first hour only.
- **Split across the cheapest hours** (`gridshift/place.py`, `place_split`).
  Offered when Nemotron reports the job is pausable and a duration is given.
  The job runs in its N cheapest hours anywhere in the window, and every hour
  it runs in is priced. Consecutive hours are grouped into runs, so the page
  can say "runs 20 hours across 3 days" and name each stretch.

The toggle beside the job form flips between them. **Their percentages are not
directly comparable**: one block is priced optimistically at its start hour,
split pays for every hour. Same job, two accounting rules — the same trap the
average / marginal-empirical split sets, one level down.

## Evidence

Development set: `eval/labeled.jsonl`, 69 hand-written rows (the original 60,
plus 9 weekday-deadline rows added with the weekday parser). Per-run results in
`results/progress.csv`; per-row detail in `results/*_eval.json`.

| what | result | baseline / note |
|---|---|---|
| Classify accuracy (69 rows) | **0.986** (68/69) | majority class ("deferable"): 0.609. The one miss is L54, "Retrain the model in 2 hours" (gold `unclear`, predicted `deferable`) |
| Classify accuracy, 60 rows, after relabel | 0.983 (59/60) | majority class: 0.550. Up from 0.917 by a **label-definition change, not a model improvement**: L21/L26/L30 relabeled, prompt and code unchanged (see FAILURES.md #7) |
| Classify accuracy, 60 rows, before relabel | 0.917 (55/60) | majority class: 0.500. 0.932 (55/59) excluding one HTTP 429 scored as "unclear" |
| Classify, ambiguous rows | 0.000 → **0.933** | before → after the label-definition fix (see FAILURES.md) |
| Classify, no-deadline rows | 0.400 → **1.000** | before → after the same fix |
| Window MAE where both parsed | **0.00 h** across 49/49 | 0.00 h in every run; optimistic: see Limitations |
| Explain fidelity (passes `verify()`, no fallback) | **0.95** (19/20) | after the tradeoff-rule change. Every number in all 20 outputs was exact; the one fallback cited a non-existent field (`water_withdrawal`) in `fields_used`, and its headline was correct. All 20 headlines were read against their signs by hand and state the right direction. Earlier runs: 1.00 (20/20) after the prompt rewrite (FAILURES.md #8), 0.90 (18/20) before it |
| Fallback template passes `verify()` | **4032/4032** | 4 seasons × 24 arrival hours × 7 windows × 3 objectives × 2 bases, offline |
| Placement tests | **150 passing** | `tests/test_timeline.py`: split picks exactly the N cheapest hours and is never beaten by any contiguous block, a 1-hour job is identical in both modes, and the strip's geometry and day labels are asserted in a real browser |
| Holdout | **sealed, not yet opened** | 30 rows, sha256 in `results/HOLDOUT_HASH.txt`; to be opened exactly once, on Sunday. No score until then |

For scale: always answering "unclear" scores 1.000 on ambiguous rows and 0.000
on standard and unusual rows. The classifier is the only thing that scores well
across all four categories.

## Limitations

- **Window MAE is optimistic.** The deadline parser was built against this same
  development set. Given the gold quotes it resolves 49/49 exactly. The 0.00 h
  is measured only where both the model's quote and the parse succeeded. The
  holdout is the honest test.
- **`verify()` checks digits, not words.** It confirms every number appears in
  `display` with the right sign. It does not catch the model attaching the
  carbon delta to the withdrawal sentence, and it cannot tell "improves" from
  "worsens": five reversed headlines once passed it (FAILURES.md #8). Direction
  is now fixed by Python-computed facts in the prompt, not checked by
  `verify()`.
- **One-block placement prices only the start hour.** A 6 h job is costed at
  the intensity of the hour it begins in, so its figures are optimistic and
  cannot be compared directly with split placement, which prices every hour it
  runs in. Split is the honest mode; one block is kept because it is what a
  non-pausable job actually does.
- **Split assumes pausing is free.** Checkpoint and restart cost time and
  energy that GridShift does not model, so a job split across many short runs
  looks cheaper than it would be.
- **Free-tier rate limits.** One HTTP 429 in the 0.917 classify run, despite
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
python3 -m uvicorn api:app --port 8600      # the app: http://localhost:8600
```

The page is one hand-written file (`static/index.html`) over a small FastAPI
wrapper (`api.py`) around the same functions the CLI uses. Nothing else runs it.

| | |
|---|---|
| Offline walkthrough | `http://localhost:8600/?demo=1` (or `?demo=short`) replays a recorded job from `static/demo_cache.json`: no network, no model call. Re-record with `python3 scripts/record_demo_cache.py` |
| Streamlit fallback | `python3 -m streamlit run app.py` — **not** `streamlit run app.py`, which may use a different interpreter without the dependencies |
| Terminal | `python3 run.py "It's 10pm. Fine-tuning overnight, need it before the 9am standup"` |
| Evals | `python3 eval/run_eval.py` (classify), `python3 eval/explain_eval.py` (explain) |
| Tests | `pip install pytest playwright` first (they are not runtime dependencies), then `python3 -m pytest tests/`. The browser cases drive Chrome and skip unless the app is running |

## Team

| name | email |
|---|---|
| Rajan Saha | rajan.saha499@gmail.com |

## Prior work disclosure

The PJM grid analysis (`pjm-water-carbon`) is separate prior research. This
repo uses it only as a data source, vendored at commit `28aecf4` as
pre-computed hourly profiles in `data/`, with no recomputation at runtime.
Everything in this repository was built during SteelHacks XIII: the classifier,
deadline parser, placer, explainer, verifier, evals and app.

## License

MIT. See [LICENSE](LICENSE).

# thirst

**Schedule your compute when the grid is less thirsty, and see what that costs
in carbon.**

Carbon-aware schedulers assume the cleanest hour is the best hour, but power
plants also draw water for cooling, and on the PJM grid the lowest-carbon hour
and the lowest-water-withdrawal hour are usually different hours. We measured
this over a full year: on the average accounting basis the two minima disagree
on 360 of 365 days, because PJM's cleanest large source (once-through-cooled
nuclear) is also its thirstiest. thirst takes a job described in plain English,
works out how long it can wait, places it in the best hour for carbon, water
withdrawal or water consumption, and shows exactly what that choice trades away,
with the accounting basis named beside every figure.

## The finding

Source: [`pjm-water-carbon`](../pjm-water-carbon) @ `28aecf4`, PJM balancing
authority, 2025-09-17 → 2026-09-16, 8,760 hours, EIA-930 generation × EIA-860
cooling types. All figures in this section are on the **average** basis
(generation-weighted intensity of the whole mix) unless marked otherwise.

- **The minima sit 6 hours apart.** On the annual-mean hourly profile, carbon
  bottoms out at hour-ending 13 and water withdrawal at hour-ending 19 (average
  basis).
- **Day by day, they almost never agree.** The min-carbon hour differs from the
  min-withdrawal hour on **360 of 365 days (98.6 %)**, with a mean gap of 6.7 h
  when they differ (average basis). If the two hours were statistically
  independent they would differ on 97.1 % of days, so the observed rate matches
  independence rather than alignment.
- **Mechanism.** Once-through-cooled nuclear delivers **13.3 % of PJM's
  generation**. It emits about 12 gCO₂/kWh but withdraws about 44,350 gal/MWh.
  Any hour that is clean *because* nuclear is a large share of the mix is also
  water-intensive, so carbon and withdrawal are negatively correlated
  (r = −0.465, average basis).
- **It does not generalize.** Of eight balancing authorities, five pass the
  cooling-data coverage gate. PJM is the only one of those five where carbon
  and withdrawal conflict. In the other four (MISO, BPAT, ERCO, SOCO) the daily
  minima coincide far more often than chance: 25–70 % of days differ against an
  85–91 % independence null (average basis). ISNE, NYIS and CISO fail coverage
  and are not counted. Across the five passing regions, once-through nuclear's
  share of generation explains the withdrawal correlation (R² = 0.82,
  p = 0.034, n = 5).
- **The basis flips the answer.** In upstream's scheduling simulation,
  carbon-optimized scheduling *increases* water withdrawal on the average basis
  (by 0.29 % to 1.87 % across 2–24 h of slack). On the marginal-empirical basis
  (the fuels that respond to an added load, with nuclear off the margin) it
  saves 3.05 % carbon and 6.37 % withdrawal at 24 h of slack. Attribution and
  causation give opposite answers, which is why thirst never shows a figure
  without its basis.

## Where Nemotron sits

Nemotron (`nvidia/nemotron-3-super-120b-a12b` on NVIDIA's hosted API) does two
jobs. Python does everything else.

**(a) Classify: plain-English workload → structured deferability.**
`thirst/classify.py`. Input: "It's 10pm. Fine-tuning overnight, need it before
the 9am standup." Output, constrained to a JSON schema server-side:

```json
{"label": "deferable", "interruptible": null,
 "window_phrase": "before the 9am standup",
 "rationale": "The job can be delayed until later tonight and still finish in time for the morning meeting."}
```

The model returns a *verbatim quote*, never a number of hours. Python checks
that the quote is a real substring of the input, then `parse_window_hours()`
resolves it against anchors in the full text ("It's Tuesday 6pm", "my flight is
Thursday at 6am") and does the arithmetic. A rationale containing a digit is
blanked.

**(b) Explain: narrate the tradeoff from a `PlacementRecord`.**
`thirst/explain.py`. Python builds the record: basis, objective, arrival and
placed hour, and per-metric baseline / placed / delta for carbon, water
withdrawal and water consumption. It also computes the tradeoff flag and a
`display` map of every figure pre-formatted as a string. Nemotron writes a
headline and 2–4 sentences using only those fields.

**The architectural rule: Nemotron never emits a number Python didn't compute.**
This is enforced mechanically by `thirst/verify.py`, not by instructions in the
prompt. Every numeric token in the model's text must match, sign included, a
string in `PlacementRecord.display`. Any sentence stating a figure must name its
accounting basis. The text may not mention outside facts (fuels, cooling,
weather) or cite a field that doesn't exist. Output with any violation is
discarded and replaced by `explain.fallback()`, a deterministic Python template.
The model can make an explanation worse, but it cannot put a wrong number in
front of the user.

## Evidence

Development set: `eval/labeled.jsonl` (60 hand-written rows). Results are
appended to `results/progress.csv`; full per-row output is in
`results/classify_eval.json` and `results/explain_eval.json`.

| what | result | baseline / note |
|---|---|---|
| Classify accuracy (60 rows) | **0.917** (55/60) | majority class ("deferable"): 0.500 |
| Classify accuracy, excluding one HTTP 429 | 0.932 (55/59) | the 429 was scored as "unclear", i.e. wrong |
| Classify, ambiguous rows | 0.000 → **0.933** | before → after the label-definition fix (see FAILURES.md) |
| Classify, no-deadline rows | 0.400 → **1.000** | before → after the same fix |
| Window MAE where both parsed | **0.00 h** in every run | optimistic: see Limitations |
| Explain numeric fidelity | **0.90** (18/20) | both failures were sign mismatches, caught by `verify()` |
| Fallback template passes `verify()` | **4032/4032** | 4 seasons × 24 arrival hours × 7 windows × 3 objectives × 2 bases, offline |
| Holdout | sealed | 30 rows, sha256 in `results/HOLDOUT_HASH.txt`; to be opened exactly once, on Sunday. Score: TODO |

Constant-classifier scores per category, for scale: always answering "unclear"
scores 1.000 on ambiguous rows and 0.000 on standard and unusual rows. The
classifier is the only thing that scores well across all four categories.

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
| TODO | TODO |
| TODO | TODO |

## Prior work disclosure

The PJM grid analysis (`pjm-water-carbon`) is separate prior research. This
repo uses it only as a data source, vendored at commit `28aecf4` as
pre-computed hourly profiles in `data/`, with no recomputation at runtime.
Everything in this repository was built during SteelHacks XIII: the classifier,
deadline parser, placer, explainer, verifier, evals and app.

## License

MIT. See [LICENSE](LICENSE).

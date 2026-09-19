# eval

Hand-written ground truth for Nemotron job #1 (classify).

| file | rows | use |
|---|---:|---|
| `labeled.jsonl` | 60 | development: prompt iteration, error analysis |
| `holdout.jsonl` | 30 | final score only; sha256 frozen in `results/HOLDOUT_HASH.txt` |

Each row: `id`, `category` (`standard | unusual | ambiguous | no_deadline`),
`text`, `label`, `window_h`, `window_phrase`.

Labeling conventions:

- `window_h` = whole hours from submission until the job must be **finished**,
  rounded down (so "in 20 minutes" is `0`). It does not subtract run time.
  The placer does that.
- Labels describe what the text states, not whether the window is usable.
  Any deadline that resolves to a number of hours is `deferable`, even when
  the window is tiny ("in 20 minutes" → `window_h` 0, "within the hour" → 1)
  or equals the run time ("takes 8 hours, due in 8 hours"). Whether a short
  window leaves room to shift is arithmetic, and arithmetic belongs in
  `place()`, not the classifier.
- `not_deferable` is only: the text says to run now with no stated window
  ("right now", "immediately", "as soon as possible"), or the job is
  real-time / interactive serving.
- Clock deadlines are anchored by a "now" stated in the text. Without one
  ("by morning", "before EOD"), the label is `unclear` and `window_h` is null.
- Exception: weekday deadlines with no stated "now" (L61–L69, e.g. "due on sunday
  3pm") are `deferable`, resolved against a submission clock the row carries
  in `now_day` / `now_hour` (the app uses the system clock).
- `window_phrase` is the shortest verbatim span that states the time
  constraint. If the text gives two conflicting constraints, the span covers
  both.
- `unusual` rows put the resolving context *outside* the phrase
  ("before I fly out" + "my flight is Thursday at 6am"), so
  `parse_window_hours(window_phrase)` alone cannot recover `window_h`.

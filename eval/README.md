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
- `not_deferable` includes jobs whose run time uses up the whole window
  ("takes 8 hours, due in 8 hours").
- Clock deadlines are anchored by a "now" stated in the text. Without one
  ("by morning", "before EOD"), the label is `unclear` and `window_h` is null.
- `window_phrase` is the shortest verbatim span that states the time
  constraint. If the text gives two conflicting constraints, the span covers
  both.
- `unusual` rows put the resolving context *outside* the phrase
  ("before I fly out" + "my flight is Thursday at 6am"), so
  `parse_window_hours(window_phrase)` alone cannot recover `window_h`.

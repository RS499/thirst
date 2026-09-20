#!/usr/bin/env python3
"""Terminal path through GridShift: classify -> place. No explainer or verifier yet.

    python run.py "fine-tuning overnight, need it before the 9am standup"

Arrival is now (local clock). Every figure printed is computed in Python and
labelled with its accounting basis.
"""
from __future__ import annotations

import sys
from datetime import datetime

from gridshift.classify import classify
from gridshift.place import place
from gridshift.signals import season_of

METRIC_NAMES = {"carbon": "carbon", "withdrawal": "water withdrawal",
                "consumption": "water consumption"}


def main(description: str) -> None:
    now = datetime.now()
    c = classify(description, now_hour=now.hour, now_dow=now.weekday())
    print("classification")
    print(f"  label          {c.label}" + (f"   (error: {c.error})" if c.error else ""))
    print(f"  interruptible  {c.interruptible}")
    print(f"  window_phrase  {c.window_phrase!r}")
    print(f"  rationale      {c.rationale or '(blank)'}")
    print(f"  window         {'unparsed' if c.window_h is None else f'{c.window_h} h'}")

    if c.label != "deferable" or not c.window_h:
        print("\nnot deferable -> run on arrival, nothing to place")
        return

    arrival = c.now_hour + 1          # hour-ending of the hour the window counts from
    records = place(arrival, c.window_h, season_of(now.month))
    first = next(iter(records.values())).display
    print(f"\nplacement  (basis: average, season {first['season']}, arrival {first['arrival.hour']}, "
          f"window {first['window_h']}, source {first['source']})")
    print("  per MWh; delta = % better than run-on-arrival, negative = worse")
    for objective, r in records.items():
        d = r.display
        print(f"\n  optimise {objective}: start {d['placed.hour']} (shift {d['shift_h']}), "
              f"tradeoff {d['tradeoff']}")
        for m, name in METRIC_NAMES.items():
            print(f"    {name:18s} {d[f'{m}.delta_pct']:>8s}  average basis   "
                  f"({d[f'{m}.baseline']} -> {d[f'{m}.placed']})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('usage: python run.py "<plain-English job description>"')
    main(sys.argv[1])

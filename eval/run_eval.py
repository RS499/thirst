#!/usr/bin/env python3
"""Classification eval over eval/labeled.jsonl. NEVER reads eval/holdout.jsonl.

    python eval/run_eval.py

Each line of labeled.jsonl:
    {"id": str, "category": "standard|ambiguous|unusual|no_deadline", "text": str,
     "label": "deferable|not_deferable|unclear", "window_h": int | null,
     "window_phrase": str | null}
The current time, where it matters, is stated inside ``text``. Rows whose
deadline needs the submission clock (a weekday with no "It's ..." clause) carry
optional ``now_day`` (e.g. "Wednesday") and ``now_hour`` (0-23) instead.

Calls are sequential with a 1 s pause (free NIM tier rate-limits). Writes
results/classify_eval.json and appends one row to results/progress.csv.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thirst.classify import LABELS, MODEL, classify, nemotron  # noqa: E402

LABELED = ROOT / "eval" / "labeled.jsonl"
RESULTS = ROOT / "results"
DELAY_S = 1.0
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def main() -> None:
    rows = [json.loads(line) for line in LABELED.read_text().splitlines() if line.strip()]
    model = nemotron()
    preds = []
    for i, row in enumerate(rows):
        if i:
            time.sleep(DELAY_S)
        c = classify(row["text"], model, now_hour=row.get("now_hour"),
                     now_dow=DAYS.index(row["now_day"].lower()) if row.get("now_day") else None)
        preds.append(c)
        mark = "ok " if c.label == row["label"] else "BAD"
        print(f"[{i + 1:>3}/{len(rows)}] {row['id']} {mark} {row['label']:>13s} -> {c.label:13s} "
              f"win {row['window_h']!s:>4s} -> {c.window_h!s:4s} {c.error or ''}", flush=True)

    n = len(rows)
    correct = sum(p.label == r["label"] for p, r in zip(preds, rows))
    confusion = Counter((r["label"], p.label) for p, r in zip(preds, rows))
    per_label = {}
    for lab in LABELS:
        tp = confusion[(lab, lab)]
        pred_n = sum(v for (_, p), v in confusion.items() if p == lab)
        true_n = sum(v for (t, _), v in confusion.items() if t == lab)
        per_label[lab] = {"precision": tp / pred_n if pred_n else None,
                          "recall": tp / true_n if true_n else None,
                          "support": true_n}

    by_category = {}
    for cat in sorted({r["category"] for r in rows}):
        idx = [i for i, r in enumerate(rows) if r["category"] == cat]
        hits = sum(preds[i].label == rows[i]["label"] for i in idx)
        by_category[cat] = {"accuracy": hits / len(idx), "correct": hits, "n": len(idx)}

    # Trivial baselines: a constant classifier per label, overall and per category.
    constant = {lab: {"overall": sum(r["label"] == lab for r in rows) / n,
                      **{cat: sum(r["label"] == lab for r in rows if r["category"] == cat)
                         / by_category[cat]["n"] for cat in by_category}}
                for lab in LABELS}
    majority = max(constant, key=lambda lab: constant[lab]["overall"])
    ok_rows = [(p, r) for p, r in zip(preds, rows) if p.error is None]

    has_truth = [(p, r) for p, r in zip(preds, rows) if r["window_h"] is not None]
    parsed = [(p, r) for p, r in has_truth if p.window_h is not None]
    errors = [abs(p.window_h - r["window_h"]) for p, r in parsed]
    metrics = {
        "accuracy": correct / n,
        "accuracy_excl_errors": (sum(p.label == r["label"] for p, r in ok_rows) / len(ok_rows)
                                 if ok_rows else None),
        "majority_baseline": {"label": majority, "accuracy": constant[majority]["overall"]},
        "constant_baselines": constant,
        "n": n,
        "api_or_parse_errors": sum(p.error is not None for p in preds),
        "by_category": by_category,
        "per_label": per_label,
        "confusion": {f"{t}->{p}": v for (t, p), v in sorted(confusion.items())},
        "window_parse_rate": len(parsed) / len(has_truth) if has_truth else None,
        "window_n_with_truth": len(has_truth),
        "window_mae_h": sum(errors) / len(errors) if errors else None,
    }

    print(f"\nlabel accuracy  {correct}/{n} = {metrics['accuracy']:.3f}   "
          f"majority baseline (always {majority}) {constant[majority]['overall']:.3f}")
    excl = metrics["accuracy_excl_errors"]
    print(f"  API/parse errors scored as unclear: {metrics['api_or_parse_errors']}"
          + (f"; accuracy excluding them {excl:.3f} (n={len(ok_rows)})" if excl is not None else ""))
    print(f"  {'category':13s} {'model':>12s}   " + "  ".join(f"always {lab[:9]:9s}" for lab in LABELS))
    for cat, s in by_category.items():
        print(f"  {cat:13s} {s['correct']:>2}/{s['n']:<2} {s['accuracy']:.3f}   "
              + "  ".join(f"{constant[lab][cat]:16.3f}" for lab in LABELS))
    print("per label")
    for lab, s in per_label.items():
        fmt = lambda x: "  n/a" if x is None else f"{x:.3f}"  # noqa: E731
        print(f"  {lab:13s} precision {fmt(s['precision'])}  recall {fmt(s['recall'])}  "
              f"support {s['support']}")
    print("confusion (true -> predicted)")
    for k, v in metrics["confusion"].items():
        print(f"  {k:30s} {v}")
    rate, mae = metrics["window_parse_rate"], metrics["window_mae_h"]
    print(f"window parse rate {len(parsed)}/{len(has_truth)}"
          + (f" = {rate:.3f}" if rate is not None else "")
          + (f"   MAE {mae:.2f} h (where both parsed)" if mae is not None else ""))

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    stamp = datetime.now().isoformat(timespec="seconds")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "classify_eval.json").write_text(json.dumps({
        "timestamp": stamp, "commit": commit, "model": MODEL, "metrics": metrics,
        "predictions": [{"truth": r, "pred": asdict(p)} for p, r in zip(preds, rows)],
    }, indent=2) + "\n")

    progress = RESULTS / "progress.csv"
    new = not progress.exists()
    with progress.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "commit", "model", "eval", "n", "accuracy",
                        "window_parse_rate", "window_mae_h", "errors", "majority_baseline"]
                   + [f"acc_{c}" for c in by_category])
        w.writerow([stamp, commit, MODEL, "classify", n, f"{metrics['accuracy']:.4f}",
                    "" if rate is None else f"{rate:.4f}", "" if mae is None else f"{mae:.3f}",
                    metrics["api_or_parse_errors"], f"{constant[majority]['overall']:.4f}"]
                   + [f"{v['accuracy']:.4f}" for v in by_category.values()])


if __name__ == "__main__":
    main()

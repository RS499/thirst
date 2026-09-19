#!/usr/bin/env python3
"""Explanation eval: numeric-fidelity of Nemotron job #2 over 20 PlacementRecords.

    python eval/explain_eval.py

Records come from ``place()`` and span both bases and every tradeoff: per basis,
4 aligned, 3 conflict and 3 neutral, drawn with a fixed seed. Each goes through
``explain()`` exactly as the app would. The numeric-fidelity rate is the fraction whose
model output passes ``verify()`` and is shown without falling back to the template.

Calls are sequential with a 1 s pause (free NIM tier rate-limits). Writes
results/explain_eval.json.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from thirst.classify import MODEL  # noqa: E402
from thirst.explain import Explanation, explain, nemotron, parse_response  # noqa: E402
from thirst.place import place  # noqa: E402
from thirst.signals import SEASONS  # noqa: E402
from thirst.verify import verify_explanation  # noqa: E402

RESULTS = ROOT / "results"
DELAY_S = 1.0
SEED = 0
PER_BASIS = {"aligned": 4, "conflict": 3, "neutral": 3}
WINDOWS = (4, 8, 12, 24)
NUMERIC_RULES = {"uncomputed_number", "sign_mismatch"}


def sample_records() -> list:
    rng = random.Random(SEED)
    chosen = []
    for basis in ("average", "marginal_empirical"):
        pool = {t: [] for t in PER_BASIS}
        for season in SEASONS:
            for arrival in range(1, 25):
                for window in WINDOWS:
                    for r in place(arrival, window, season, basis=basis).values():
                        pool[r.tradeoff].append(r)
        for tradeoff, k in PER_BASIS.items():
            chosen += rng.sample(pool[tradeoff], k)
    return chosen


def main() -> None:
    records = sample_records()
    model = nemotron()
    rows = []
    for i, rec in enumerate(records):
        if i:
            time.sleep(DELAY_S)
        raw: list[str] = []

        def capture(prompt: str) -> str:
            raw.append(model(prompt))
            return raw[-1]

        out = explain(rec, capture)
        violations = []
        if out.fallback and raw:
            try:
                d = parse_response(raw[0])
                violations = [asdict(v) for v in verify_explanation(
                    rec, Explanation(d["headline"], d["explanation"], d["fields_used"]))]
            except Exception:                                # noqa: BLE001 -- counted below
                pass
        rows.append({"job_id": rec.job_id, "basis": rec.basis, "objective": rec.objective,
                     "tradeoff": rec.tradeoff, "passed": not out.fallback,
                     "api_or_parse_error": out.fallback and not violations,
                     "violations": violations, "error": out.error,
                     "raw_model_output": raw[0] if raw else None,
                     "shown": asdict(out), "display": rec.display})
        print(f"[{i + 1:>2}/{len(records)}] {rec.basis:18s} {rec.tradeoff:8s} "
              f"{'pass' if not out.fallback else 'FALLBACK'} "
              f"{sorted({v['rule'] for v in violations}) if violations else out.error or ''}",
              flush=True)

    n = len(rows)
    passed = sum(r["passed"] for r in rows)

    def rate(sub):
        return {"passed": sum(r["passed"] for r in sub), "n": len(sub),
                "rate": sum(r["passed"] for r in sub) / len(sub) if sub else None}

    rule_counts = Counter(v["rule"] for r in rows for v in r["violations"])
    metrics = {
        "numeric_fidelity_rate": passed / n,
        "passed": passed,
        "n": n,
        # Outputs whose numbers were all display tokens, whatever else they broke.
        "numbers_clean_rate": sum(not r["api_or_parse_error"]
                                  and not any(v["rule"] in NUMERIC_RULES for v in r["violations"])
                                  for r in rows) / n,
        "api_or_parse_errors": sum(r["api_or_parse_error"] for r in rows),
        "by_basis": {b: rate([r for r in rows if r["basis"] == b])
                     for b in ("average", "marginal_empirical")},
        "by_tradeoff": {t: rate([r for r in rows if r["tradeoff"] == t]) for t in PER_BASIS},
        "violation_rule_counts": dict(rule_counts.most_common()),
        "outputs_with_violation": {rule: sum(any(v["rule"] == rule for v in r["violations"])
                                             for r in rows) for rule in rule_counts},
    }

    print(f"\nnumeric-fidelity {passed}/{n} = {metrics['numeric_fidelity_rate']:.3f}   "
          f"numbers clean {metrics['numbers_clean_rate']:.3f}   "
          f"API/parse errors {metrics['api_or_parse_errors']}")
    for group in ("by_basis", "by_tradeoff"):
        for k, s in metrics[group].items():
            print(f"  {k:18s} {s['passed']:>2}/{s['n']:<2} {s['rate']:.3f}")
    for rule, c in metrics["outputs_with_violation"].items():
        print(f"  outputs with {rule:18s} {c}")

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "explain_eval.json").write_text(json.dumps({
        "timestamp": datetime.now().isoformat(timespec="seconds"), "commit": commit,
        "model": MODEL, "seed": SEED, "metrics": metrics, "records": rows,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()

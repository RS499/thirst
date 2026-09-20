#!/usr/bin/env python3
"""Record static/demo_cache.json: the demo's offline replay of one preset.

    python3 -m uvicorn api:app --port 8600      # in another shell
    python3 scripts/record_demo_cache.py

Calls the live API once for classify, then place and one explain per
combination (2 bases x 3 objectives) in each run mode, so ?demo=1 needs no
network and makes no model call. The preset text and its duration are read from static/index.html,
so the recording always matches the button a judge would click.

Re-record whenever a display string changes shape (a new field, a new time
format): the demo replays what was recorded, so stale entries show stale text.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PAGE, OUT = ROOT / "static" / "index.html", ROOT / "static" / "demo_cache.json"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8600"
BASES, OBJECTIVES = ("average", "marginal_empirical"), ("carbon", "water_withdrawal", "water_consumption")


def preset() -> tuple[str, int]:
    """The first EXAMPLES entry in the page: its text and duration in hours."""
    m = re.search(r'const EXAMPLES = \[\s*\["[^"]*",\s*"(.+?)",\s*(\d+)\]', PAGE.read_text())
    if not m:
        sys.exit("could not read the first preset from static/index.html")
    return m.group(1).replace("\\'", "'"), int(m.group(2))


def main() -> None:
    text, duration = preset()
    with httpx.Client(base_url=URL, timeout=120) as http:
        def post(path: str, body: dict) -> dict:
            r = http.post(path, json=body)
            r.raise_for_status()
            return r.json()

        classify = post("/classify", {"text": text})
        if classify["label"] != "deferable" or not classify["window_h"]:
            sys.exit(f"preset did not classify as deferable: {classify}")
        request = {"arrival_hour": classify["arrival_hour"], "window_h": classify["window_h"],
                   "season": classify["season"], "duration_h": duration, "power_kw": None,
                   "now_dow": classify["now_dow"]}
        place = post("/place", request)
        explain = {f"{b}|{o}": post("/explain", {**request, "basis": b, "objective": o})
                   for b in BASES for o in OBJECTIVES}
        # The same job run in its cheapest hours, for the tour's split step. The
        # contiguous entries above are untouched.
        split_req = {**request, "mode": "split"}
        place_split = post("/place", split_req)
        explain_split = {f"{b}|{o}": post("/explain", {**split_req, "basis": b, "objective": o})
                         for b in BASES for o in OBJECTIVES}

    for key, e in explain.items():
        print(f"  {key:34s} {'template' if e['fallback'] else 'Nemotron'}: {e['headline']}")

    OUT.write_text(json.dumps({
        "_note": "Recorded by scripts/record_demo_cache.py. The demo replays these responses "
                 "so it runs with no network and no model call. Re-record when display "
                 "strings change shape.",
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.strip(),
        "model": classify["display"]["model"],
        "preset": text, "request": request, "classify": classify, "place": place,
        "explain": explain, "place_split": place_split, "explain_split": explain_split,
    }, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: window {classify['window_h']} h, duration {duration} h, "
          f"{len(explain)} + {len(explain_split)} explanations")


if __name__ == "__main__":
    main()

"""thirst HTTP API + the static frontend (static/index.html).

Wraps thirst.classify / place / explain unchanged. Python formats every figure
the page shows; the page only lays them out (and sizes bars from the same
Python-computed deltas).

    python3 -m uvicorn api:app --port 8600

POST /classify  plain-English job -> Classification (+ arrival, season)
POST /place     arrival/window/season -> all 6 PlacementRecords (2 bases x 3
                objectives) with the pure-Python fallback() text for each, so
                switching objective or basis never calls the model
POST /explain   one record -> Nemotron explanation, verified (or the template)
GET  /live      PJM's latest EIA-930 fuel mix -> intensities, average basis.
                Display only: never feeds placement, which reads the vendored
                profiles. 503 on any failure; the page hides the bar.
GET  /evidence  provenance, eval scores and the five-region table, from files
"""
from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from thirst.classify import MODEL, classify
from thirst.explain import BASIS_PROSE, explain, fallback
from thirst.place import OBJECTIVES, place
from thirst.signals import load_profile, season_of

ROOT = Path(__file__).resolve().parent
DATA, RESULTS, STATIC = ROOT / "data", ROOT / "results", ROOT / "static"
BASES = ("average", "marginal_empirical")
METRICS = ("carbon", "withdrawal", "consumption")
UPSTREAM_COMMIT = "28aecf4462732f522229508d68c8dee3c30e5bca"

app = FastAPI(title="thirst", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------- classify / place

class ClassifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/classify")
def classify_route(body: ClassifyIn) -> dict:
    now = datetime.now()
    t0 = time.perf_counter()
    c = classify(body.text, now_hour=now.hour, now_dow=now.weekday())
    elapsed = time.perf_counter() - t0
    return {**asdict(c), "arrival_hour": c.now_hour + 1, "season": season_of(now.month),
            "display": {"now": f"{c.now_hour:02d}:00",
                        "window_h": "unparsed" if c.window_h is None else f"{c.window_h} h",
                        "model": MODEL.split("/")[-1], "latency": f"{elapsed:.1f} s"}}


class PlaceIn(BaseModel):
    arrival_hour: int = Field(ge=1, le=24)
    window_h: int = Field(ge=0)
    season: str
    duration_h: int | None = Field(default=None, ge=1, le=24)
    power_kw: float | None = Field(default=None, gt=0)


def _start_window(window_h: int, duration_h: int | None) -> int:
    """Start slots that still finish by the deadline (place() prices 1-hour starts)."""
    return max(window_h - (duration_h or 1) + 1, 1)


def _record_json(rec, energy_mwh: float | None) -> dict:
    out = {"basis": rec.basis, "objective": rec.objective, "tradeoff": rec.tradeoff,
           "placed_hour": rec.placed["hour"], "shift_h": rec.shift_h,
           "delta": {m: getattr(rec, m).delta_pct for m in METRICS},
           "display": dict(rec.display), "fallback": asdict(fallback(rec))}
    if energy_mwh:
        # Job-level totals: per-MWh start-hour prices x the job's energy, in Python.
        for m in METRICS:
            o = getattr(rec, m)
            saved = (o.baseline - o.placed) * energy_mwh
            out["display"][f"job.{m}.saved"] = f"{saved:+,.1f} {o.units}"
        out["display"]["job.energy_mwh"] = f"{energy_mwh:,.2f} MWh"
    return out


@app.post("/place")
def place_route(body: PlaceIn) -> dict:
    if body.season not in ("DJF", "MAM", "JJA", "SON"):
        raise HTTPException(422, "season must be DJF, MAM, JJA or SON")
    if body.duration_h and body.duration_h >= body.window_h:
        # Nothing to choose: the job needs the whole window or more.
        return {"refusal": {"duration": f"{body.duration_h} h", "window": f"{body.window_h} h",
                            "late": body.duration_h > body.window_h}}
    start_window = _start_window(body.window_h, body.duration_h)
    energy = (body.power_kw * body.duration_h / 1000
              if body.power_kw and body.duration_h else None)
    records = {b: {obj: _record_json(r, energy) for obj, r in
                   place(body.arrival_hour, start_window, body.season, basis=b).items()}
               for b in BASES}
    # One bar scale for every basis and objective, so switching moves bars
    # through the centre line instead of silently rescaling them.
    scale = max(abs(v) for b in records.values() for r in b.values()
                for v in r["delta"].values()) or 1.0
    return {"records": records, "scale": scale, "start_window_h": start_window,
            "basis_prose": BASIS_PROSE}


class ExplainIn(PlaceIn):
    basis: str
    objective: str


@app.post("/explain")
def explain_route(body: ExplainIn) -> dict:
    if body.basis not in BASES or body.objective not in OBJECTIVES:
        raise HTTPException(422, "unknown basis or objective")
    rec = place(body.arrival_hour, _start_window(body.window_h, body.duration_h),
                body.season, basis=body.basis)[body.objective]
    t0 = time.perf_counter()
    e = explain(rec)
    return {**asdict(e), "display": {"latency": f"{time.perf_counter() - t0:.1f} s"}}


# ---------------------------------------------------------------- live grid state

EIA_URL = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"
EIA_BUCKETS = {"COL": "coal", "NG": "gas", "NUC": "nuclear", "OIL": "oil", "OTH": "other",
               "SUN": "solar", "WND": "wind", "WAT": "hydro", "GEO": "geothermal"}
# Storage codes (battery, pumped storage, ...) are excluded, as upstream does:
# they move energy in time and go negative while charging.
LIVE_TTL_S = 600                         # DEMO_KEY allows ~30 requests/hour
_live_cache: dict = {"at": 0.0, "body": None}


def _factors() -> dict[str, dict[str, float]]:
    with (DATA / "fuel_factors.csv").open() as f:
        return {r["bucket"]: {"carbon": float(r["carbon_gco2_kwh"]),
                              "withdrawal": float(r["withdrawal_gal_mwh"]),
                              "consumption": float(r["consumption_gal_mwh"])}
                for r in csv.DictReader(f)}


def _fetch_live() -> dict:
    params = {"api_key": os.environ.get("EIA_API_KEY", "DEMO_KEY"), "frequency": "hourly",
              "data[0]": "value", "facets[respondent][]": "PJM",
              "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "60"}
    # httpx verifies TLS with certifi; python.org Python's urllib has no CA bundle.
    r = httpx.get(EIA_URL, params=params, timeout=8)
    r.raise_for_status()
    rows = r.json()["response"]["data"]

    by_period: dict[str, dict[str, float]] = {}
    for row in rows:
        bucket = EIA_BUCKETS.get(row["fueltype"])
        if bucket and row["value"] is not None:
            mix = by_period.setdefault(row["period"], {})
            mix[bucket] = mix.get(bucket, 0.0) + max(float(row["value"]), 0.0)
    # Latest hour that reports the three big fuels (the newest hour can be partial).
    period = next(p for p in sorted(by_period, reverse=True)
                  if {"coal", "gas", "nuclear"} <= set(by_period[p]))
    mix = by_period[period]
    total = sum(mix.values())
    fac = _factors()
    intensity = {m: sum(mw * fac[b][m] for b, mw in mix.items()) / total for m in METRICS}

    ts = datetime.strptime(period, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    fuels = sorted(mix, key=lambda b: mix[b], reverse=True)
    return {
        "period_utc": ts.isoformat(),
        "age_hours": age_h,
        "mix": [{"bucket": b, "share": mix[b] / total,
                 "display": {"share": f"{100 * mix[b] / total:.0f} %", "mw": f"{mix[b]:,.0f} MW"}}
                for b in fuels],
        "display": {
            "carbon": f"{intensity['carbon']:,.0f}",
            "withdrawal": f"{intensity['withdrawal']:,.0f}",
            "consumption": f"{intensity['consumption']:,.0f}",
            "total": f"{total:,.0f} MW",
            "timestamp": ts.strftime("%Y-%m-%d %H:00 UTC"),
            "age": f"{age_h:.0f} h ago",
            "basis": "average",
        },
    }


@app.get("/live")
def live() -> dict:
    now = time.time()
    if _live_cache["body"] is None or now - _live_cache["at"] > LIVE_TTL_S:
        try:
            _live_cache.update(at=now, body=_fetch_live())
        except Exception as e:                               # noqa: BLE001
            if _live_cache["body"] is None:
                raise HTTPException(503, f"EIA live pull failed: {type(e).__name__}") from e
    return _live_cache["body"]


# ---------------------------------------------------------------- evidence

@app.get("/evidence")
def evidence() -> dict:
    with (RESULTS / "progress.csv").open() as f:
        runs = [r for r in csv.DictReader(f) if r["eval"] == "classify"]
    cls = runs[-1]
    ex = json.loads((RESULTS / "explain_eval.json").read_text())["metrics"]
    hours = int(load_profile("hourly", "average")["n_hours"].sum())
    holdout = (RESULTS / "HOLDOUT_HASH.txt").read_text().split()[0]

    with (RESULTS / "regional_water_stress.csv").open() as f:
        regions = [{
            "region": r["region"],
            "rank_raw": int(r["rank_consumption"]),
            "rank_stress": int(r["rank_stress_adjusted_consumption"]),
            "display": {
                "withdrawal": f"{float(r['withdrawal_l_per_mwh']):,.0f}",
                "consumption": f"{float(r['consumption_l_per_mwh']):,.0f}",
                "stress_factor": f"{float(r['stress_factor']):.2f}",
                "stress_adjusted": f"{float(r['stress_adjusted_consumption_l_eq_per_mwh']):,.0f}",
            }} for r in csv.DictReader(f)]

    return {
        "provenance": [
            ["Source", f"pjm-water-carbon @ {UPSTREAM_COMMIT[:7]}"],
            ["Profiles", f"EIA-930 hourly, 2025-09-17 → 2026-09-16 · {hours:,}\u00a0h"],
            ["Cooling", "EIA-860 2025 (Y2025) generator cooling types"],
            ["Carbon", "IPCC AR5 WG3 Annex III, Table A.III.2 lifecycle medians "
                       "(oil, other: not AR5)"],
            ["Water", "Macknick et al. 2012, Environ. Res. Lett. 7 045802"],
            ["Stress", "AWARE-US, Lee et al. 2019, Sci. Total Environ. 648:1313"],
        ],
        "classifier": {
            "accuracy": f"{float(cls['accuracy']):.3f}",
            "baseline": f"{float(cls['majority_baseline']):.3f}",
            "n": cls["n"], "commit": cls["commit"],
            "accuracy_value": float(cls["accuracy"]),
            "baseline_value": float(cls["majority_baseline"]),
        },
        "explainer": {
            "fidelity": f"{ex['numeric_fidelity_rate']:.2f}",
            "passed": f"{ex['passed']}/{ex['n']}",
            "fidelity_value": ex["numeric_fidelity_rate"],
        },
        "holdout": f"sealed · sha256 {holdout[:12]}…",
        "model": MODEL,
        "regions": sorted(regions, key=lambda r: r["rank_raw"]),
    }


# ---------------------------------------------------------------- static

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/demo_cache.json")
def demo_cache() -> FileResponse:
    """Recorded responses for the ?demo=1 walkthrough; see static/demo_cache.json."""
    return FileResponse(STATIC / "demo_cache.json")


@app.get("/charts/{name}")
def chart(name: str) -> FileResponse:
    if name not in ("divergence.png", "region_reorder.png"):
        raise HTTPException(404)
    return FileResponse(RESULTS / name)

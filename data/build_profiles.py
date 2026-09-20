#!/usr/bin/env python3
"""ONE-OFF vendoring script. Never imported or run by GridShift at runtime.

Vendored from: pjm-water-carbon @ 28aecf4462732f522229508d68c8dee3c30e5bca
    ("Extend to eight balancing authorities: the conflict is fleet-specific")

Rebuilds the four profile CSVs in this directory by importing the upstream
repo's own ``run_savings.build_signals`` read-only -- no upstream logic is
re-implemented here, so the vendored numbers are upstream's numbers. Requires a
checkout of pjm-water-carbon at the commit above with its data/raw/ populated.

    PYTHONDONTWRITEBYTECODE=1 python3 data/build_profiles.py ~/pjm-water-carbon

Profiles are means over the upstream window 2025-09-17 -> 2026-09-16 (PJM BA,
fleet EIA-860 cooling mix, hydro evaporation excluded -- the upstream headline
configuration). Hour is EIA-930 hour-ENDING, 1..24 local; the single hour 25 on
the DST fall-back day is dropped (one sample cannot define a profile row).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent
SEASON_NAMES = ["DJF", "MAM", "JJA", "SON"]
DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
COLS = {"carbon": "carbon_gco2_kwh", "consumption": "consumption_gal_mwh",
        "withdrawal": "withdrawal_gal_mwh"}
BASES = ("average", "marginal_empirical")


def main(upstream: Path) -> None:
    sys.dont_write_bytecode = True            # leave the upstream tree untouched
    sys.path.insert(0, str(upstream))
    import run_savings as rs                  # noqa: E402  (upstream module)
    from pjmwater.eia930 import load_pjm_generation

    gen = load_pjm_generation(upstream / "data" / "raw", rs.START, rs.END)
    bases, _, _, _ = rs.build_signals(gen)

    frame = pd.DataFrame({
        "season": ((gen["date"].dt.month % 12) // 3).map(dict(enumerate(SEASON_NAMES))),
        "dow": gen["date"].dt.dayofweek.map(dict(enumerate(DOW_NAMES))),
        "hour": gen["hour"].astype(int),
    })
    for basis in BASES:
        sig = frame.copy()
        for metric, col in COLS.items():
            sig[col] = bases[basis][metric]
        sig = sig[sig["hour"] <= 24]

        for name, keys in (("hourly", ["season", "hour"]),
                           ("weekly", ["season", "dow", "hour"])):
            prof = sig.groupby(keys, sort=False)[list(COLS.values())].mean()
            prof.insert(0, "n_hours", sig.groupby(keys, sort=False).size())
            prof = prof.reset_index()
            prof["season"] = pd.Categorical(prof["season"], SEASON_NAMES, ordered=True)
            if "dow" in prof:
                prof["dow"] = pd.Categorical(prof["dow"], DOW_NAMES, ordered=True)
            prof = prof.sort_values(keys).reset_index(drop=True)
            path = OUT / f"profile_{name}_{basis}.csv"
            prof.to_csv(path, index=False, float_format="%.4f")
            print(f"wrote {path.name}: {len(prof)} rows")

        # Cross-check against upstream's published signal stats.
        for metric, col in COLS.items():
            print(f"  {basis:18s} {metric:11s} mean {sig[col].mean():10.3f}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "~/pjm-water-carbon").expanduser())

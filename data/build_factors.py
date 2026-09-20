#!/usr/bin/env python3
"""ONE-OFF vendoring script. Never imported or run by GridShift at runtime.

Vendored from: pjm-water-carbon @ 28aecf4462732f522229508d68c8dee3c30e5bca

Writes data/fuel_factors.csv: the per-fuel-bucket factors behind the average-
basis profiles -- carbon from upstream CARBON_FACTORS (IPCC AR5 medians for six
buckets; oil and other documented upstream as non-AR5), water from upstream's
EIA-860 fleet cooling mix (Macknick et al. factors), hydro evaporation excluded
(the upstream headline configuration). Taken from ``run_savings.build_signals``
so they are exactly the numbers the vendored profiles were built from.

api.py uses them for the display-only "PJM right now" bar. They never feed
placement, which reads the profiles.

    PYTHONDONTWRITEBYTECODE=1 python3 data/build_factors.py ~/pjm-water-carbon
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "fuel_factors.csv"


def main(upstream: Path) -> None:
    sys.dont_write_bytecode = True            # leave the upstream tree untouched
    sys.path.insert(0, str(upstream))
    import run_savings as rs                  # noqa: E402  (upstream module)
    from pjmwater.carbon_factors import CARBON_FACTORS
    from pjmwater.eia930 import load_pjm_generation

    gen = load_pjm_generation(upstream / "data" / "raw", rs.START, rs.END)
    _, _, _, water = rs.build_signals(gen)
    buckets = sorted(set(CARBON_FACTORS) | set(water["withdrawal"]))
    df = pd.DataFrame({
        "bucket": buckets,
        "carbon_gco2_kwh": [CARBON_FACTORS.get(b, 0.0) for b in buckets],
        "withdrawal_gal_mwh": [water["withdrawal"].get(b, 0.0) for b in buckets],
        "consumption_gal_mwh": [water["consumption"].get(b, 0.0) for b in buckets],
    })
    df.to_csv(OUT, index=False, float_format="%.4f")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "~/pjm-water-carbon").expanduser())

# Vendored from pjm-water-carbon @ 28aecf4462732f522229508d68c8dee3c30e5bca
# (local repo ~/pjm-water-carbon, no remote; "Extend to eight balancing
# authorities: the conflict is fleet-specific"). The CSVs this module reads were
# produced once by data/build_profiles.py from upstream's run_savings.build_signals;
# nothing here recomputes them.
"""Load pre-computed PJM carbon- and water-intensity profiles.

Read-only access to the vendored profile CSVs in ``data/``. There is NO
recomputation at runtime and no EIA fetch: every number served here was computed
upstream and frozen into a CSV.

Two accounting bases are available, and they answer different questions:

``average``
    Generation-weighted mean intensity of the whole mix. Attribution: how clean
    was the grid in this hour? On this basis carbon and water withdrawal
    conflict in PJM, because nuclear is low-carbon but water-intensive.
``marginal_empirical``
    Intensity of the dispatchable fuels (coal, gas, oil, other) estimated to
    respond to an added kWh, per (season x hour-of-day) bin. Causation: what
    changes if a job moves? Because it only varies by season and hour, its
    weekly profile repeats across weekdays by construction.

Water is always reported as two separate metrics, never combined:
``withdrawal_gal_mwh`` (water taken in) and ``consumption_gal_mwh`` (water not
returned). Carbon is ``carbon_gco2_kwh``.

Hours are EIA-930 hour-ENDING, 1..24, PJM local time.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

Basis = Literal["average", "marginal_empirical"]
Granularity = Literal["hourly", "weekly"]

BASES: tuple[Basis, ...] = ("average", "marginal_empirical")
GRANULARITIES: tuple[Granularity, ...] = ("hourly", "weekly")
METRICS = {
    "carbon": "carbon_gco2_kwh",
    "consumption": "consumption_gal_mwh",
    "withdrawal": "withdrawal_gal_mwh",
}
UNITS = {"carbon": "gCO2/kWh", "consumption": "gal/MWh", "withdrawal": "gal/MWh"}
SEASONS = ("DJF", "MAM", "JJA", "SON")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SOURCE = "pjm-water-carbon@28aecf4"


@lru_cache(maxsize=None)
def load_profile(granularity: Granularity, basis: Basis) -> pd.DataFrame:
    """Return one vendored profile as a DataFrame.

    ``hourly`` rows are keyed by (season, hour); ``weekly`` rows by
    (season, dow, hour). Columns: ``n_hours`` (sample count behind each mean)
    plus one column per metric in ``METRICS``. The returned frame is cached;
    copy it before mutating.
    """
    if granularity not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}, got {granularity!r}")
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}, got {basis!r}")
    return pd.read_csv(DATA / f"profile_{granularity}_{basis}.csv")


def season_of(month: int) -> str:
    """Meteorological season label (DJF/MAM/JJA/SON) for a 1-based month."""
    return SEASONS[(month % 12) // 3]

#!/usr/bin/env python3
"""ONE-OFF: AWARE-US water-stress weighting of the five coverage-passing regions.

Never imported or run by GridShift at runtime.

    PYTHONDONTWRITEBYTECODE=1 python3 data/build_water_stress.py ~/pjm-water-carbon

1. Normalises data/raw/"AWARE US Model.xlsx" (Argonne AWARE-US county factors,
   Lee et al. 2019, Sci. Total Environ. 648:1313-1322) to
   data/raw/aware_us_county.csv (state, county, fips, cf), dropping the -1.0
   no-data sentinel.
2. Joins the factors to EIA-860 generators via upstream's own
   ``cooling_mix.load_fleet`` and ``water_stress.regional_stress_factor``
   (pjm-water-carbon @ 28aecf4, imported read-only). EIA-860 carries no county
   FIPS, so the join is on normalised state + county name.
3. Writes results/regional_water_stress.csv: raw withdrawal and consumption
   (L/MWh, average basis, from upstream results/regions.csv) and
   stress-adjusted consumption, with a rank for each.

Stress weighting applies to CONSUMPTION only, following upstream: AWARE
characterises water removed from a basin, and withdrawal that is returned is not
the same impact.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
REGIONS = ["PJM", "MISO", "ERCO", "SOCO", "BPAT"]   # passed upstream's cooling-coverage gate
MIN_MATCH_PCT = 95.0   # below this, too much consuming capacity is unweighted to report


def county_key(name: str) -> str:
    """Normalise a county name so EIA-860 and AWARE spellings meet."""
    s = str(name).casefold().strip()
    s = re.sub(r"\b(county|parish|borough|census area|municipality)\b", "", s)
    s = re.sub(r"\bst\.?\s", "saint ", s)
    s = re.sub(r"\bste\.?\s", "sainte ", s)
    return re.sub(r"[^a-z]", "", s)


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    order = np.argsort(values.to_numpy())
    v, w = values.to_numpy()[order], weights.to_numpy()[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, cum[-1] / 2)])


def build_aware() -> pd.DataFrame:
    df = pd.read_excel(RAW / "AWARE US Model.xlsx", sheet_name="Data", header=None,
                       skiprows=2, usecols=range(4), dtype=str,
                       names=["fips", "state", "county", "cf"])
    df["cf"] = pd.to_numeric(df["cf"], errors="coerce")
    n = len(df)
    sentinel = df["cf"] == -1.0
    print(f"AWARE rows {n}, states {df['state'].nunique()}; "
          f"dropped {int(sentinel.sum())} with cf = -1.0 (no data), "
          f"{int(df['cf'].isna().sum())} non-numeric")
    df = df[~sentinel & df["cf"].notna()].copy()
    df["state"] = df["state"].str.strip().str.upper()
    df["county"] = df["county"].str.strip()
    df[["state", "county", "fips", "cf"]].to_csv(RAW / "aware_us_county.csv", index=False)
    print(f"wrote data/raw/aware_us_county.csv: {len(df)} rows, cf range "
          f"{df['cf'].min():.3f}-{df['cf'].max():.3f}")
    return df


def main(upstream: Path) -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(upstream))
    from pjmwater.cooling_mix import load_fleet
    from pjmwater.water_stress import CONSUMING_BUCKETS, regional_stress_factor, to_litres_per_mwh

    aware = build_aware()
    # Upstream's join is on (state, casefolded county); feed it normalised keys on both sides.
    aware_keyed = pd.DataFrame({"state": aware["state"], "county": aware["county"].map(county_key),
                                "cf": aware["cf"]})
    dup = aware_keyed.duplicated(["state", "county"], keep=False)
    if dup.any():   # e.g. a Virginia city and county of the same name
        print(f"  {int(dup.sum())} AWARE rows share a normalised key; their cf is averaged:",
              sorted(set(aware.loc[dup, "state"] + ":" + aware.loc[dup, "county"]))[:10])
        aware_keyed = aware_keyed.groupby(["state", "county"], as_index=False)["cf"].mean()

    regions = pd.read_csv(upstream / "results" / "regions.csv")
    rows = []
    for ba in REGIONS:
        fleet = load_fleet(upstream / "data" / "raw" / "eia860", ba)
        fleet["county"] = fleet["county"].map(county_key)
        s = regional_stress_factor(fleet, aware_keyed)

        sub = fleet[fleet["bucket"].isin(CONSUMING_BUCKETS)
                    & fleet["cooling"].notna() & (fleet["cooling"] != "none")]
        keys = set(zip(aware_keyed["state"], aware_keyed["county"]))
        miss = sub[[(st, c) not in keys for st, c in zip(sub["state"], sub["county"])]]
        miss_mw = miss.groupby(["state", "county"])["capacity_mw"].sum().sort_values(ascending=False)

        # Robustness: AWARE caps factors at 100, and a few capped counties can
        # dominate a capacity-weighted mean. Report the weighted median and the
        # share of the mean that comes from capped counties.
        hit = sub.merge(aware_keyed, on=["state", "county"])
        cf_median = weighted_median(hit["cf"], hit["capacity_mw"])
        weighted = hit["cf"] * hit["capacity_mw"]
        capped_share = 100 * weighted[hit["cf"] >= 100].sum() / weighted.sum()

        r = regions[(regions["region"] == ba) & (regions["basis"] == "average")].set_index("metric")
        cons_l = to_litres_per_mwh(r.at["consumption", "mean_water_gal_mwh"])
        with_l = to_litres_per_mwh(r.at["withdrawal", "mean_water_gal_mwh"])
        ok = s["matched_capacity_pct"] >= MIN_MATCH_PCT
        rows.append({
            "region": ba,
            "withdrawal_l_per_mwh": with_l,
            "consumption_l_per_mwh": cons_l,
            "stress_factor": s["stress_factor"],
            "stress_factor_wmedian": cf_median,
            "cf_share_from_capped_counties_pct": capped_share,
            "consuming_capacity_mw": sub["capacity_mw"].sum(),
            "matched_capacity_pct": s["matched_capacity_pct"],
            "match_ok": ok,
            "stress_adjusted_consumption_l_eq_per_mwh": cons_l * s["stress_factor"] if ok else float("nan"),
            "stress_adjusted_consumption_wmedian_l_eq_per_mwh": cons_l * cf_median if ok else float("nan"),
        })
        print(f"{ba}: consuming capacity {sub['capacity_mw'].sum():,.0f} MW, matched "
              f"{s['matched_capacity_pct']:.2f} %, cf {s['stress_factor']:.3f}"
              + ("" if miss_mw.empty else f"; unmatched {dict(miss_mw.head(6).round(0))}"))

    out = pd.DataFrame(rows)
    for col, rank in (("withdrawal_l_per_mwh", "rank_withdrawal"),
                      ("consumption_l_per_mwh", "rank_consumption"),
                      ("stress_adjusted_consumption_l_eq_per_mwh", "rank_stress_adjusted_consumption"),
                      ("stress_adjusted_consumption_wmedian_l_eq_per_mwh",
                       "rank_stress_adjusted_consumption_wmedian")):
        out[rank] = out[col].rank(ascending=False).astype("Int64")
    out.to_csv(ROOT / "results" / "regional_water_stress.csv", index=False, float_format="%.4f")
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "~/pjm-water-carbon").expanduser())

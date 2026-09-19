# data/: vendored profiles

**Origin:** `pjm-water-carbon` @ `28aecf4462732f522229508d68c8dee3c30e5bca`
("Extend to eight balancing authorities: the conflict is fleet-specific").
Built once by `build_profiles.py`, which imports upstream's own
`run_savings.build_signals`. No upstream logic is re-implemented here. That
script is never run or imported by thirst at runtime.

**Window:** PJM BA, 2025-09-17 → 2026-09-16. Upstream headline configuration:
EIA-860 fleet cooling mix, hydro reservoir evaporation excluded.

| file | rows | keyed by |
|---|---:|---|
| `profile_hourly_average.csv` | 96 | season, hour |
| `profile_hourly_marginal_empirical.csv` | 96 | season, hour |
| `profile_weekly_average.csv` | 672 | season, dow, hour |
| `profile_weekly_marginal_empirical.csv` | 672 | season, dow, hour |

**Columns:** `n_hours` (samples behind each mean), `carbon_gco2_kwh`,
`consumption_gal_mwh`, `withdrawal_gal_mwh`. Withdrawal and consumption are
separate metrics and are never summed.

**Notes**

- `season` ∈ DJF / MAM / JJA / SON. `hour` is EIA-930 hour-ending, 1–24, PJM
  local time. The single hour 25 (DST fall-back) is dropped.
- `average` = generation-weighted mean intensity of the whole mix (attribution).
- `marginal_empirical` = Siler-Evans regression of Δfuel on Δdispatchable
  generation per (season × hour) bin, with response set coal/gas/oil/other
  (causation). It only varies by season × hour, so **its weekly profile repeats
  across weekdays by construction**.
- The `marginal_flat_ngcc` basis is deliberately not vendored. It is constant in
  every hour, so all timing savings are 0 % by arithmetic.
- Cross-check vs. upstream `results/signal_stats_by_basis.csv` (annual means):
  average matches exactly; marginal-empirical differs in the third decimal
  because of the dropped hour 25.

Rebuild (requires upstream checkout with `data/raw/` populated):

    PYTHONDONTWRITEBYTECODE=1 python3 data/build_profiles.py ~/pjm-water-carbon

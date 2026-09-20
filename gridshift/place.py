"""Pure-Python placement: pick the cheapest start hour in a window, per objective.

Reads the vendored hour-of-day profile for ``basis`` (default average) through
``signals`` and builds one ``PlacementRecord`` per objective. The job is priced as one MWh
delivered in a single hour, so ``baseline``/``placed`` are per-MWh totals
(kg CO2e and gallons) and ``delta_pct`` does not depend on job size.

Hours are EIA-930 hour-ENDING, 1..24: hour-ending ``h`` is the interval that
starts at clock ``h-1``:00. Candidate starts are ``arrival`` .. ``arrival +
window_h - 1`` (the job must finish by the deadline), wrapping past midnight
within the same season's profile. The profile repeats daily, so windows longer
than ``PROFILE_H`` search the same 24 hours; ``window_h`` is still reported as given.

``place_split`` is the second mode, for a pausable job of known duration: it runs
in the N cheapest hours anywhere in the window rather than as one block, and
prices every hour it runs in (the contiguous path prices the start hour only).
"""
from __future__ import annotations

from gridshift.explain import MetricOutcome, PlacementRecord
from gridshift.signals import METRICS, SOURCE, Basis, load_profile

BASIS = "average"
OBJECTIVES = {"carbon": "carbon", "water_withdrawal": "withdrawal",
              "water_consumption": "consumption"}
# Per-MWh totals: g/kWh x 1,000 kWh / 1,000 = kg per MWh; gal/MWh x 1 MWh = gal.
UNITS = {"carbon": "kg CO2e", "consumption": "gal", "withdrawal": "gal"}
ENERGY_MWH = 1.0
DURATION_H = 1
PROFILE_H = 24


def clock(hour: int) -> str:
    """12-hour label for a clock hour 0-23: 0 -> "12 AM", 14 -> "2 PM"."""
    return f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"


def _clock(hour_ending: int) -> str:
    return clock(hour_ending - 1)


def _tradeoff(deltas: dict[str, float]) -> str:
    """conflict: at least one metric improves and at least one worsens.
    aligned: at least one improves and none worsens. neutral: none changes.

    Judged on the one-decimal values that are displayed, so the flag can never
    contradict the numbers printed beside it.
    """
    shown = [round(v, 1) for v in deltas.values()]
    better, worse = any(v > 0 for v in shown), any(v < 0 for v in shown)
    if better and worse:
        return "conflict"
    return "aligned" if better else "neutral"


def _record(prof, objective: str, arrival_hour: int, window_h: int, season: str,
            basis: str, *, placed_hour: int, shift: int, duration_h: int,
            hours: tuple[int, ...], mode: str, base_hours: tuple[int, ...],
            run_hours: tuple[int, ...]) -> PlacementRecord:
    """One record. Each metric is the mean intensity over the hours actually run.

    For a single hour that mean is the hour itself, so the contiguous path is
    unchanged. ``base_hours``/``run_hours`` are hour-ending numbers: running on
    arrival, and the placement.
    """
    def mean(col: str, hs: tuple[int, ...]) -> float:
        return sum(float(prof.at[h, col]) for h in hs) / len(hs) * ENERGY_MWH

    outcomes, deltas = {}, {}
    for m, c in METRICS.items():
        base, new = mean(c, base_hours), mean(c, run_hours)
        deltas[m] = (base - new) / base * 100
        outcomes[m] = MetricOutcome(UNITS[m], base, new, deltas[m])
    tradeoff = _tradeoff(deltas)

    display = {
        "basis": basis, "objective": objective, "season": season,
        "arrival.hour": _clock(arrival_hour), "placed.hour": _clock(placed_hour),
        "shift_h": f"{shift} h", "window_h": f"{window_h} h",
        "duration_h": f"{duration_h} h", "energy_mwh": f"{ENERGY_MWH:g} MWh",
        "tradeoff": tradeoff, "source": SOURCE,
        # How the job runs, in words the explainer may quote. A one-hour job is one
        # block in either mode, so both modes say the same thing about it.
        "mode": "one block" if len(hours) == 1 else f"split across {len(hours)} separate hours",
    }
    if mode == "split":
        display["hours_n"] = f"{len(hours)} hours"
    for m, o in outcomes.items():
        display[f"{m}.units"] = o.units
        display[f"{m}.baseline"] = f"{o.baseline:,.1f} {o.units}"
        display[f"{m}.placed"] = f"{o.placed:,.1f} {o.units}"
        display[f"{m}.delta_pct"] = f"{o.delta_pct:+.1f} %"

    return PlacementRecord(
        job_id=f"{season}-he{arrival_hour}-w{window_h}-{objective}" + ("-split" if mode == "split" else ""),
        basis=basis, objective=objective, season=season,
        arrival={"hour": arrival_hour}, placed={"hour": placed_hour},
        shift_h=shift, window_h=window_h, duration_h=duration_h, energy_mwh=ENERGY_MWH,
        carbon=outcomes["carbon"], consumption=outcomes["consumption"],
        withdrawal=outcomes["withdrawal"], tradeoff=tradeoff, source=SOURCE,
        display=display, mode=mode, hours=hours)


def _season_profile(season: str, basis: str):
    prof = load_profile("hourly", basis)
    return prof[prof["season"] == season].set_index("hour")


def place_split(arrival_hour: int, window_h: int, season: str, duration_h: int,
                basis: Basis = BASIS) -> dict[str, PlacementRecord]:
    """Run a pausable job in its ``duration_h`` cheapest hours inside the window.

    Candidate hours are the offsets 0 .. window_h - 1 from ``arrival`` (i.e. up to
    the deadline); a window longer than a day may pick the same clock hour on two
    days, which is what a pausable job would really do. The baseline is the same
    number of hours run back to back from arrival. Both sides are the mean
    intensity over the hours run, so every hour is priced, not just the first.
    """
    prof = _season_profile(season, basis)
    n = max(1, min(duration_h, window_h))
    hour_at = {off: (arrival_hour - 1 + off) % 24 + 1 for off in range(max(window_h, 1))}
    base_hours = tuple(hour_at[off] for off in range(min(n, len(hour_at))))

    records = {}
    for objective, metric in OBJECTIVES.items():
        col = METRICS[metric]
        chosen = sorted(sorted(hour_at, key=lambda o: (prof.at[hour_at[o], col], o))[:n])
        records[objective] = _record(
            prof, objective, arrival_hour, window_h, season, basis,
            placed_hour=hour_at[chosen[0]], shift=chosen[0], duration_h=n,
            hours=tuple(chosen), mode="split", base_hours=base_hours,
            run_hours=tuple(hour_at[o] for o in chosen))
    return records


def place(arrival_hour: int, window_h: int, season: str,
          basis: Basis = BASIS) -> dict[str, PlacementRecord]:
    """Best start hour in the window for each objective, as PlacementRecords.

    ``arrival_hour`` is hour-ending 1..24. ``window_h`` 0 or 1 leaves only the
    arrival hour, so every delta is 0 and the tradeoff is neutral.
    """
    prof = _season_profile(season, basis)
    shifts = range(min(max(window_h, 1), PROFILE_H))
    hour_at = {s: (arrival_hour - 1 + s) % 24 + 1 for s in shifts}

    records = {}
    for objective, metric in OBJECTIVES.items():
        col = METRICS[metric]
        shift = min(shifts, key=lambda s: (prof.at[hour_at[s], col], s))  # ties -> earliest
        placed_hour = hour_at[shift]
        records[objective] = _record(
            prof, objective, arrival_hour, window_h, season, basis,
            placed_hour=placed_hour, shift=shift, duration_h=DURATION_H,
            hours=(shift,), mode="contiguous",
            base_hours=(arrival_hour,), run_hours=(placed_hour,))
    return records

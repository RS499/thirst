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
"""
from __future__ import annotations

from thirst.explain import MetricOutcome, PlacementRecord
from thirst.signals import METRICS, SOURCE, Basis, load_profile

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


def _tradeoff(deltas: dict[str, float], optimised: str) -> str:
    """aligned: every other metric improves; conflict: any other metric worsens.

    Judged on the one-decimal values that are displayed, so the flag can never
    contradict the numbers printed beside it.
    """
    if round(deltas[optimised], 1) == 0:
        return "neutral"
    others = [round(v, 1) for m, v in deltas.items() if m != optimised]
    if any(v < 0 for v in others):
        return "conflict"
    return "aligned" if all(v > 0 for v in others) else "neutral"


def place(arrival_hour: int, window_h: int, season: str,
          basis: Basis = BASIS) -> dict[str, PlacementRecord]:
    """Best start hour in the window for each objective, as PlacementRecords.

    ``arrival_hour`` is hour-ending 1..24. ``window_h`` 0 or 1 leaves only the
    arrival hour, so every delta is 0 and the tradeoff is neutral.
    """
    prof = load_profile("hourly", basis)
    prof = prof[prof["season"] == season].set_index("hour")
    shifts = range(min(max(window_h, 1), PROFILE_H))
    hour_at = {s: (arrival_hour - 1 + s) % 24 + 1 for s in shifts}

    records = {}
    for objective, metric in OBJECTIVES.items():
        col = METRICS[metric]
        shift = min(shifts, key=lambda s: (prof.at[hour_at[s], col], s))  # ties -> earliest
        placed_hour = hour_at[shift]

        outcomes, deltas = {}, {}
        for m, c in METRICS.items():
            base = float(prof.at[arrival_hour, c]) * ENERGY_MWH
            new = float(prof.at[placed_hour, c]) * ENERGY_MWH
            deltas[m] = (base - new) / base * 100
            outcomes[m] = MetricOutcome(UNITS[m], base, new, deltas[m])
        tradeoff = _tradeoff(deltas, metric)

        display = {
            "basis": basis, "objective": objective, "season": season,
            "arrival.hour": _clock(arrival_hour), "placed.hour": _clock(placed_hour),
            "shift_h": f"{shift} h", "window_h": f"{window_h} h",
            "duration_h": f"{DURATION_H} h", "energy_mwh": f"{ENERGY_MWH:g} MWh",
            "tradeoff": tradeoff, "source": SOURCE,
        }
        for m, o in outcomes.items():
            display[f"{m}.units"] = o.units
            display[f"{m}.baseline"] = f"{o.baseline:,.1f} {o.units}"
            display[f"{m}.placed"] = f"{o.placed:,.1f} {o.units}"
            display[f"{m}.delta_pct"] = f"{o.delta_pct:+.1f} %"

        records[objective] = PlacementRecord(
            job_id=f"{season}-he{arrival_hour}-w{window_h}-{objective}", basis=basis,
            objective=objective, season=season,
            arrival={"hour": arrival_hour}, placed={"hour": placed_hour},
            shift_h=shift, window_h=window_h, duration_h=DURATION_H, energy_mwh=ENERGY_MWH,
            carbon=outcomes["carbon"], consumption=outcomes["consumption"],
            withdrawal=outcomes["withdrawal"], tradeoff=tradeoff, source=SOURCE,
            display=display)
    return records

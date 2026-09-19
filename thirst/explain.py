"""Nemotron job #2: explain a placement's carbon/water tradeoff in plain English.

The model receives ONE placement record, computed entirely by Python, and writes
a short explanation using ONLY fields from that record. It may not introduce a
number, a fuel, a mechanism, or a comparison that the record does not contain.
Every number it may print is pre-formatted by Python in ``record.display``; the
model copies those strings, it does not round, convert, or derive.

Output schema (see CLAUDE.md, "explain"):

    {
      "headline": "<one sentence>",
      "explanation": "<two to four sentences>",
      "fields_used": ["<dotted path into the placement record>", ...]
    }
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

Basis = Literal["average", "marginal_empirical"]
Objective = Literal["carbon", "water_consumption", "water_withdrawal"]
Tradeoff = Literal["aligned", "conflict", "neutral"]
ModelFn = Callable[[str], str]

EXPLAIN_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "explanation", "fields_used"],
    "properties": {
        "headline": {"type": "string"},
        "explanation": {"type": "string"},
        "fields_used": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
}


@dataclass(frozen=True)
class MetricOutcome:
    """One metric's totals for run-on-arrival vs. the chosen placement."""

    units: str                    # "kg CO2e" or "gal"
    baseline: float
    placed: float
    delta_pct: float              # (baseline - placed) / baseline * 100; + = saved


@dataclass(frozen=True)
class PlacementRecord:
    """Everything the explainer is allowed to talk about. Built by Python only."""

    job_id: str
    basis: Basis                  # accounting basis; MUST be named beside any figure
    objective: Objective
    season: str
    arrival: dict                 # {"hour": 15}  hour-ending, 1..24
    placed: dict                  # {"hour": 19}
    shift_h: int
    window_h: int
    duration_h: int
    energy_mwh: float
    carbon: MetricOutcome
    consumption: MetricOutcome
    withdrawal: MetricOutcome
    tradeoff: Tradeoff            # computed: does optimising the objective cost another metric?
    source: str                   # e.g. "pjm-water-carbon@28aecf4"
    display: dict[str, str]       # dotted field path -> exact string the model may print


@dataclass(frozen=True)
class Explanation:
    headline: str
    explanation: str
    fields_used: list[str]


def build_prompt(record: PlacementRecord) -> str:
    """Render the explanation prompt: the record's ``display`` map plus rules."""
    raise NotImplementedError


def parse_response(raw: str) -> dict:
    """Parse and schema-validate raw model text against ``EXPLAIN_SCHEMA``."""
    raise NotImplementedError


def fallback(record: PlacementRecord) -> Explanation:
    """Deterministic template explanation, used when verification fails."""
    raise NotImplementedError


def explain(record: PlacementRecord, model: ModelFn) -> Explanation:
    """Explain one placement: prompt, call, validate, verify, else ``fallback``."""
    raise NotImplementedError

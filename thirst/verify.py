"""Deterministic guards on everything Nemotron returns.

Nothing the model writes reaches a user without passing through here. The two
project rules are enforced mechanically, not by prompt wording alone:

1. **No un-computed numbers.** Every numeric token in model text must match a
   string Python placed in ``PlacementRecord.display`` (explain), or appear
   verbatim in the user's own input (classify).
2. **No savings figure without its basis.** Any sentence that states a figure
   from ``carbon`` / ``consumption`` / ``withdrawal`` must name the record's
   accounting basis ("average" or "marginal-empirical").

A non-empty violation list means the caller discards the model output.
"""
from __future__ import annotations

from dataclasses import dataclass

from thirst.classify import Classification
from thirst.explain import Explanation, PlacementRecord


@dataclass(frozen=True)
class Violation:
    rule: str                     # "uncomputed_number" | "basis_missing" | "unknown_field" | ...
    detail: str


def extract_numbers(text: str) -> list[str]:
    """Return every numeric token in ``text`` (integers, decimals, percents, signs)."""
    raise NotImplementedError


def allowed_numbers(record: PlacementRecord) -> set[str]:
    """Normalised set of numeric tokens the explainer may print for ``record``."""
    raise NotImplementedError


def verify_classification(description: str, result: Classification) -> list[Violation]:
    """Check ``window_phrase`` is a verbatim substring and ``rationale`` has no digits."""
    raise NotImplementedError


def verify_explanation(record: PlacementRecord, result: Explanation) -> list[Violation]:
    """Apply both project rules plus a ``fields_used`` existence check."""
    raise NotImplementedError

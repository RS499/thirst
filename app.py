"""thirst -- water-aware scheduling of deferrable compute on the PJM grid.

Pipeline for one request:

    plain-English job  --classify (Nemotron)-->  Classification
                       --place (Python)-------->  PlacementRecord
                       --explain (Nemotron)---->  Explanation
                       --verify (Python)------->  shown to user, or fallback

Python owns every number. Nemotron only labels (classify) and narrates
(explain), and ``thirst.verify`` rejects any output that breaks the rules in
CLAUDE.md.
"""
from __future__ import annotations

from thirst.classify import Classification, ModelFn
from thirst.explain import Basis, Explanation, Objective, PlacementRecord


def make_model() -> ModelFn:
    """Return a prompt -> text callable bound to the configured Nemotron endpoint."""
    raise NotImplementedError


def place(
    job: Classification,
    *,
    arrival_dow: str,
    arrival_hour: int,
    season: str,
    duration_h: int,
    power_kw: float,
    basis: Basis,
    objective: Objective,
) -> PlacementRecord:
    """Choose the cheapest feasible start within ``job.window_h`` and build the record.

    Pure Python over ``thirst.signals`` profiles. Energy is fixed: only the
    start hour moves, never duration or power.
    """
    raise NotImplementedError


def handle(description: str, **job_params) -> tuple[PlacementRecord | None, Explanation | None]:
    """Run the full pipeline for one description; ``(None, None)`` if not deferable."""
    raise NotImplementedError


def main() -> None:
    """Entry point (UI / CLI to be decided)."""
    raise NotImplementedError


if __name__ == "__main__":
    main()

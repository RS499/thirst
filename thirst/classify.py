"""Nemotron job #1: classify a job's deferability from plain English.

The model reads a user's description of a workload ("nightly retraining, needs
to be done before the 9am standup") and returns a label plus the VERBATIM phrase
that states its time flexibility. It never returns a number of hours: Python
parses ``window_phrase`` into ``window_h`` (see ``parse_window_hours``), so the
only numbers that reach the scheduler are ones Python computed.

Output schema (see CLAUDE.md, "classify"):

    {
      "label": "deferable" | "not_deferable" | "unclear",
      "interruptible": true | false | null,
      "window_phrase": "<verbatim substring of the input>" | null,
      "rationale": "<one sentence, no digits>"
    }
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

Label = Literal["deferable", "not_deferable", "unclear"]
ModelFn = Callable[[str], str]   # prompt -> raw model text (Nemotron endpoint)

CLASSIFY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["label", "interruptible", "window_phrase", "rationale"],
    "properties": {
        "label": {"enum": ["deferable", "not_deferable", "unclear"]},
        "interruptible": {"type": ["boolean", "null"]},
        "window_phrase": {"type": ["string", "null"]},
        "rationale": {"type": "string", "pattern": "^[^0-9]*$"},
    },
}


@dataclass(frozen=True)
class Classification:
    """Validated model output plus the Python-derived window."""

    label: Label
    interruptible: bool | None
    window_phrase: str | None
    rationale: str
    window_h: int | None          # computed by parse_window_hours, never by the model


def build_prompt(description: str) -> str:
    """Render the classification prompt for one plain-English job description."""
    raise NotImplementedError


def parse_response(raw: str) -> dict:
    """Parse and schema-validate raw model text against ``CLASSIFY_SCHEMA``."""
    raise NotImplementedError


def parse_window_hours(window_phrase: str | None) -> int | None:
    """Convert a verbatim flexibility phrase to whole hours of slack, in Python.

    Returns None when the phrase is absent or cannot be parsed unambiguously;
    the caller then treats the job as not deferable rather than guessing.
    """
    raise NotImplementedError


def classify(description: str, model: ModelFn) -> Classification:
    """Classify one job end to end: prompt, call, validate, derive ``window_h``."""
    raise NotImplementedError

"""Nemotron job #1: classify a job's deferability from plain English.

The model reads a user's description of a workload ("nightly retraining, needs
to be done before the 9am standup") and returns a label plus the VERBATIM phrase
that states its time flexibility. It never returns a number of hours: Python
parses ``window_phrase`` into ``window_h`` (see ``parse_window_hours``), so the only
numbers that reach the scheduler are ones Python computed.

Output schema (see CLAUDE.md, "classify"):

    {
      "label": "deferable" | "not_deferable" | "unclear",
      "interruptible": true | false | null,
      "window_phrase": "<verbatim substring of the input>" | null,
      "rationale": "<one sentence, no digits>"
    }
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

Label = Literal["deferable", "not_deferable", "unclear"]
ModelFn = Callable[[str], str]   # prompt -> raw model text (Nemotron endpoint)

LABELS = ("deferable", "not_deferable", "unclear")
BASE_URL = "https://integrate.api.nvidia.com/v1"
# nvidia/nvidia-nemotron-nano-9b-v2 reached end of life on NIM on 2026-08-26
# (HTTP 410). nemotron-3-super is the Nemotron model that answered in seconds.
MODEL = "nvidia/nemotron-3-super-120b-a12b"
TEMPERATURE = 0.1

# "no rush" / "whenever" with no anchor anywhere in the text: at least a full day.
# The vendored profiles repeat daily, so more slack would offer no extra hour.
NO_DEADLINE_H = 24
MEETING_HOUR = 9                 # "before the standup" with no time given -> 9am
TONIGHT_END_HOUR = 6             # "tonight" / "overnight" -> done by 6am

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

PROMPT = """You label compute jobs for a scheduler. The label is about what the TEXT STATES,
not about whether the job could in principle wait.

Return ONLY a JSON object:
{{"label": "deferable" | "not_deferable" | "unclear",
  "interruptible": true | false | null,
  "window_phrase": string | null,
  "rationale": string}}

Labels:
- "deferable": the text states a deadline that resolves to a number of hours from now:
  a duration ("within a day and a half", "in three days"), a clock or day deadline with
  the current time stated ("It's 7pm ... by 6am tomorrow"), or an event whose time the
  text gives elsewhere ("before the audit" + "the audit is Friday at noon").
- "not_deferable": the text says it must run now (immediately, ASAP, someone is waiting,
  minutes away), or the job is real-time / interactive serving.
- "unclear": timing words with no resolvable deadline ("sometime soon", "before EOD",
  "in a bit", "tonight", "by morning", "before the demo" with no time given), OR no
  timing at all for a batch job.
RULE: if you cannot point to text that resolves to a number of hours, the label is
"unclear", never "deferable".

Fields:
- interruptible: true only if the text says it can pause/resume or checkpoint; false if
  it says it cannot; otherwise null.
- window_phrase: copy, character for character, the shortest words from the description
  that state its deadline or timing. Copy exactly; do not paraphrase. null if none.
- rationale: one sentence. Do NOT write any digits or numbers.

Examples:

Job: "Rebuild the product-image thumbnails. It's 7pm now and they must be ready by 6am tomorrow."
{{"label": "deferable", "interruptible": null, "window_phrase": "by 6am tomorrow",
  "rationale": "The current time and a clock deadline are both stated, so the window is computable."}}

Job: "Refresh the churn scores sometime later today if the cluster frees up."
{{"label": "unclear", "interruptible": null, "window_phrase": "sometime later today",
  "rationale": "The timing is vague and gives no deadline that resolves to hours."}}

Job: "Train a gradient-boosted model on the new clickstream features."
{{"label": "unclear", "interruptible": null, "window_phrase": null,
  "rationale": "A batch job with no timing stated at all."}}

Job description:
{description}"""


@dataclass(frozen=True)
class Classification:
    """Validated model output plus the Python-derived window."""

    label: Label
    interruptible: bool | None
    window_phrase: str | None
    rationale: str
    window_h: int | None          # computed by parse_window_hours, never by the model
    error: str | None = None      # why the result fell back to "unclear", if it did
    now_hour: int | None = None   # clock hour (0-23) window_h counts from: stated in text, else caller's


def client():
    """OpenAI-compatible client for NVIDIA's hosted Nemotron, shared by classify and explain.

    The SDK retries 5xx and 429 with exponential backoff and jitter.
    """
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    return OpenAI(base_url=BASE_URL, api_key=os.environ["NVIDIA_API_KEY"],
                  max_retries=5)  # free tier returns transient 503 "overloaded"


def nemotron() -> ModelFn:
    """Return a prompt -> text callable bound to NVIDIA's hosted Nemotron."""
    client_ = client()

    # Server-side schema constraint; the no-digits rule is not expressible there
    # reliably, so it is enforced in Python in classify().
    schema = {**CLASSIFY_SCHEMA, "properties": {**CLASSIFY_SCHEMA["properties"],
                                                "rationale": {"type": "string"}}}

    def call(prompt: str) -> str:
        # nemotron-3-super ignores "/no_think" and reasons inside ``content``
        # until max_tokens; enable_thinking=False is what turns reasoning off.
        r = client_.chat.completions.create(
            model=MODEL, temperature=TEMPERATURE, max_tokens=400,
            response_format={"type": "json_schema",
                             "json_schema": {"name": "classification", "schema": schema}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content or ""
    return call


def build_prompt(description: str) -> str:
    """Render the classification prompt for one plain-English job description."""
    return PROMPT.format(description=description)


def parse_response(raw: str) -> dict:
    """Extract the JSON object from raw model text (fences, think blocks, prose)."""
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)
    text = re.sub(r"```(?:json)?", "", text)
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("no JSON object in model output")
    return json.loads(match.group(0))


_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "ten": 10, "twelve": 12, "a couple of": 2, "a few": 3, "an": 1, "a": 1}
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Weekday spellings -> 0 (Monday) .. 6 (Sunday), matching datetime.weekday().
_DAY_ALIASES = {**{d: i for i, d in enumerate(_DAYS)},
                **{a: i for i, names in enumerate((("mon",), ("tue", "tues"), ("wed", "weds"),
                                                    ("thu", "thur", "thurs"), ("fri",), ("sat",),
                                                    ("sun",))) for a in names}}
_DAY = r"\b(" + "|".join(sorted(_DAY_ALIASES, key=len, reverse=True)) + r")(?:['’]?s)?\.?"
DAY_ONLY_HOUR = 9          # "by Friday" with no time: 9am, the earliest plausible deadline
_UNIT_H = {"minute": 1 / 60, "min": 1 / 60, "hour": 1, "hr": 1, "day": 24, "week": 168}

_N = r"(\d+|" + "|".join(sorted(_NUM, key=len, reverse=True)) + r")"
_UNIT = r"\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)\b"
# A relative span needs a deadline cue on one side, so "takes about 3 hours" is
# a duration, not a deadline.
_REL_BEFORE = re.compile(r"\b(?:in|within|next|every|over the next|in the next)\s+" + _N + _UNIT)
_REL_AFTER = re.compile(r"\b" + _N + _UNIT + r"\s+(?:later|from now)")
_TIME = r"(?:(\d{1,2})(?::\d{2})?\s*(am|pm|a\.m\.|p\.m\.)(?![a-z0-9])|(noon|midnight))"
_WHEN = re.compile(r"(?:" + _DAY + r"\s+(?:at\s+)?)?" + _TIME
                   + r"(?:\s+on\s+the\s+(\d{1,2})(?:st|nd|rd|th))?(\s+tomorrow)?")
_NOW = re.compile(r"\bit['’]?s\s+(?:now\s+)?" + _WHEN.pattern)
# A weekday with no time, after a deadline cue ("by Friday", "next Tuesday").
_DAY_ONLY = re.compile(r"\b(?:by|on|before|due|until|till|next|this|coming)\s+"
                       r"(?:(next|this|coming)\s+)?" + _DAY + r"(?!\s*(?:at\s+)?\d)")


def _when(m: re.Match) -> tuple[int | None, int, int | None, bool]:
    """(day-of-week, clock hour, day-of-month, tomorrow) from a _WHEN/_NOW match."""
    day, num, ampm, word, dom, tomorrow = m.groups()
    hour = (int(num) % 12 + (12 if ampm.startswith("p") else 0)) if num else \
        (12 if word == "noon" else 0)
    return (_DAY_ALIASES[day] if day else None, hour, int(dom) if dom else None, bool(tomorrow))


def _hours_until(clock_hour: int, now: int, next_day: bool = False) -> int:
    """Hours from clock hour ``now`` (0-23) until the next ``clock_hour`` o'clock."""
    h = (clock_hour - now) % 24
    return h + 24 if next_day and clock_hour > now else (h or 24)


def _hours_to_weekday(dow: int, hour: int, now_dow: int, now_hour: int,
                      next_week: bool = False) -> int:
    """Hours until the NEXT ``dow`` at ``hour``; today counts only if the hour is ahead."""
    days = (dow - now_dow) % 7
    if days == 0 and (hour <= now_hour or next_week):
        days = 7
    return days * 24 + hour - now_hour


def _anchor(text: str, now: tuple) -> int | None:
    """Hours until the first relative span or dated/clock deadline in ``text``."""
    m = _REL_BEFORE.search(text) or _REL_AFTER.search(text)
    if m:
        n, unit = m.group(1), m.group(2).rstrip("s")
        return int((int(n) if n.isdigit() else _NUM[n]) * _UNIT_H[unit])
    m = _WHEN.search(text)
    now_dow, now_hour, now_dom = now
    if now_hour is None:
        return None
    if not m:
        d = _DAY_ONLY.search(text)
        if d is None or now_dow is None:
            return None
        return _hours_to_weekday(_DAY_ALIASES[d.group(2)], DAY_ONLY_HOUR, now_dow, now_hour,
                                 next_week=d.group(0).startswith("next") or d.group(1) == "next")
    dow, hour, dom, tomorrow = _when(m)
    tomorrow = tomorrow or "tomorrow" in text
    if dom is not None and now_dom is not None:
        return (dom - now_dom) * 24 + hour - now_hour
    if dow is not None:
        if now_dow is None:
            return None
        return _hours_to_weekday(dow, hour, now_dow, now_hour)
    return _hours_until(hour, now_hour, next_day=tomorrow)


def parse_window_hours(full_text: str, window_phrase: str | None,
                       now_hour: int | None = None, now_dow: int | None = None) -> int | None:
    """Hours from now until the job's deadline, parsed and computed in Python.

    ``window_phrase`` is the model's verbatim quote; ``full_text`` supplies the
    anchors a relative phrase leaves out ("before I fly out" + "my flight is
    Thursday at 6am"). The current time comes from an "It's <day> <time>"
    clause in the text, else from ``now_hour`` (local clock, 0-23) and
    ``now_dow`` (0 = Monday, as ``datetime.weekday()``); without them, clock and
    weekday deadlines cannot be resolved. A weekday deadline takes the next
    occurrence of that day; today counts only if its hour is still ahead.

    Resolution order: the phrase itself; then deadline anchors elsewhere in the
    text (the "It's ..." clause excluded); then vague no-deadline words. 0 means
    run now. None -- no phrase, or nothing parseable -- means not deferable.
    """
    if not window_phrase:
        return None
    text, p = full_text.lower(), window_phrase.lower()
    m = _NOW.search(text)
    stated = _when(m)[:3] if m else (None, None, None)
    now = (stated[0] if stated[0] is not None else now_dow,
           stated[1] if m else now_hour, stated[2])
    rest = text[:m.start()] + text[m.end():] if m else text

    if re.search(r"\b(asap|as soon as possible|immediately|right now|right away|urgent)\b", p):
        return 0
    if "within the hour" in p:
        return 1
    hours = _anchor(p, now)
    if hours is not None:
        return hours
    named = (MEETING_HOUR if re.search(r"standup|stand-up|meeting|before work|first thing"
                                       r"|start of (the )?day|morning", p)
             else TONIGHT_END_HOUR if re.search(r"tonight|overnight|over ?night", p)
             else 17 if re.search(r"end of (the )?(business )?day|\beod\b|close of business", p)
             else 12 if re.search(r"noon|lunch", p) else None)
    if named is not None and now[1] is not None:
        return _hours_until(named, now[1])
    hours = _anchor(rest, now)
    if hours is not None:
        return hours
    # Week-scale words, after explicit anchors so "over the weekend ... back
    # Monday 8am" still resolves to Monday 8am.
    if now[0] is not None and now[1] is not None:
        if re.search(r"\bend of (the )?(work ?)?week\b|\beow\b", p):
            return _hours_to_weekday(4, 17, now[0], now[1])        # Friday 17:00
        if re.search(r"\bby the weekend\b", p):
            return _hours_to_weekday(5, 0, now[0], now[1])         # Saturday 00:00
        if re.search(r"\b(this|over the|the|on the)? ?weekend\b", p):
            return _hours_to_weekday(0, 0, now[0], now[1])         # end of Sunday
    if re.search(r"no rush|no hurry|whenever|no deadline|any ?time|not urgent|end of (the )?week"
                 r"|this week|when convenient", p):
        return NO_DEADLINE_H
    return None


def classify(description: str, model: ModelFn | None = None,
             now_hour: int | None = None, now_dow: int | None = None) -> Classification:
    """Classify one job end to end. Never raises: any failure -> label "unclear".

    ``now_hour`` is the caller's wall-clock hour; a time stated in the text
    ("It's 10pm now") overrides it. The hour actually used is returned as
    ``Classification.now_hour`` so placement starts where the window starts.
    ``now_dow`` is the caller's weekday (0 = Monday); a caller that passes a
    wall-clock ``now_hour`` without one gets the system weekday. With no clock
    at all (the eval), weekday deadlines resolve only from the text.
    """
    if now_dow is None and now_hour is not None:
        now_dow = datetime.now().weekday()
    stated = _NOW.search(description.lower())
    now_hour = _when(stated)[1] if stated else now_hour
    try:
        raw = (model or nemotron())(build_prompt(description))
        data = parse_response(raw)
    except Exception as e:                                   # noqa: BLE001 -- never raise
        return Classification("unclear", None, None, "", None,
                              error=f"{type(e).__name__}: {e}", now_hour=now_hour)

    label = data.get("label") if data.get("label") in LABELS else "unclear"
    interruptible = data.get("interruptible") if isinstance(data.get("interruptible"), bool) else None
    phrase = data.get("window_phrase")
    phrase = phrase if isinstance(phrase, str) and phrase and phrase in description else None
    rationale = data.get("rationale") if isinstance(data.get("rationale"), str) else ""
    rationale = "" if re.search(r"\d", rationale) else rationale
    return Classification(label, interruptible, phrase, rationale,
                          parse_window_hours(description, phrase, now_hour, now_dow),
                          now_hour=now_hour)

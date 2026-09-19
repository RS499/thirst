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

from dataclasses import dataclass, replace
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
    fallback: bool = False        # True: the model output was discarded for the template
    error: str | None = None      # why it was discarded, if it was


BASIS_PROSE = {"average": "average", "marginal_empirical": "marginal-empirical"}
METRIC_PROSE = {"carbon": "carbon", "withdrawal": "water withdrawal",
                "consumption": "water consumption"}
OBJECTIVE_PROSE = {"carbon": "carbon", "water_withdrawal": "water withdrawal",
                   "water_consumption": "water consumption"}

PROMPT = """You explain one compute-job placement to a non-expert. Python already did all
the maths. Your job is words only.

RECORD (field path -> the exact string you may print):
{display}

Meaning of the fields:
- The job arrived at arrival.hour and was moved to placed.hour to minimise `objective`.
- For carbon, withdrawal and consumption: baseline = running on arrival, placed = at
  placed.hour. delta_pct is the percentage LESS than running on arrival: a positive value
  means the placement is better on that metric, a negative value means it is worse.
- tradeoff: "aligned" = every metric improves; "conflict" = optimising the objective makes
  another metric worse; "neutral" = little or nothing changes.
- Water withdrawal and water consumption are two different metrics. Never add them or
  call either one just "water".

Rules (output that breaks any rule is thrown away):
1. Every number you write must be one of the RECORD strings above, copied character for
   character, including its "+" or "-" sign, commas and units (e.g. write "-1.4 %", never
   "1.4 %" or "1.4%"). Do not round, convert units, subtract, compare sizes, rank or count.
   Write the value only, never the field path ("+3.1 %", not "withdrawal.delta_pct: +3.1 %").
2. EVERY sentence that states a carbon, withdrawal or consumption figure must itself
   contain the words "{basis} basis", even if an earlier sentence already said so.
   Good: "On the {basis} basis, water withdrawal is -1.2 %."
   Bad:  "Water withdrawal is -1.2 %."
   Never mention any other accounting basis.
3. Use only the RECORD. Say nothing about fuels, power plants, cooling, PJM, weather or
   anything else that is not a field above.
4. headline: exactly one sentence. explanation: two to four sentences.
5. fields_used: the field paths (from the RECORD) you drew on.

Return ONLY a JSON object:
{{"headline": string, "explanation": string, "fields_used": [string, ...]}}"""


def nemotron() -> ModelFn:
    """Return a prompt -> text callable bound to Nemotron, constrained to ``EXPLAIN_SCHEMA``."""
    from thirst.classify import MODEL, TEMPERATURE, client

    client_ = client()

    def call(prompt: str) -> str:
        r = client_.chat.completions.create(
            model=MODEL, temperature=TEMPERATURE, max_tokens=600,
            response_format={"type": "json_schema",
                             "json_schema": {"name": "explanation", "schema": EXPLAIN_SCHEMA}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content or ""
    return call


def build_prompt(record: PlacementRecord) -> str:
    """Render the explanation prompt: the record's ``display`` map plus rules."""
    display = "\n".join(f"  {k}: {v}" for k, v in record.display.items())
    return PROMPT.format(display=display, basis=BASIS_PROSE[record.basis])


def parse_response(raw: str) -> dict:
    """Parse and schema-validate raw model text against ``EXPLAIN_SCHEMA``."""
    from thirst.classify import parse_response as extract_json

    data = extract_json(raw)
    if set(data) != set(EXPLAIN_SCHEMA["required"]):
        raise ValueError(f"keys {sorted(data)} != {EXPLAIN_SCHEMA['required']}")
    if not (isinstance(data["headline"], str) and isinstance(data["explanation"], str)):
        raise ValueError("headline and explanation must be strings")
    fields = data["fields_used"]
    if not (isinstance(fields, list) and fields and all(isinstance(f, str) for f in fields)):
        raise ValueError("fields_used must be a non-empty list of strings")
    return data


def fallback(record: PlacementRecord) -> Explanation:
    """Deterministic template explanation, used when verification fails."""
    d, b = record.display, BASIS_PROSE[record.basis]
    arr, new, obj = d["arrival.hour"], d["placed.hour"], OBJECTIVE_PROSE[record.objective]
    # Same one-decimal test as place._tradeoff, so the words match the printed signs.
    worse = [METRIC_PROSE[m] for m in METRIC_PROSE if round(getattr(record, m).delta_pct, 1) < 0]

    if record.placed == record.arrival:
        headline = f"The best start in the window is the arrival hour, {arr}, so the job stays put."
    elif record.tradeoff == "conflict":
        headline = (f"Starting at {new} instead of {arr} lowers {obj} but makes "
                    f"{' and '.join(worse)} worse ({b} basis).")
    elif record.tradeoff == "aligned":
        headline = (f"Starting at {new} instead of {arr} lowers carbon, water withdrawal "
                    f"and water consumption ({b} basis).")
    else:
        headline = f"Starting at {new} instead of {arr} changes little ({b} basis)."

    deltas = ", ".join(f"{METRIC_PROSE[m]} {d[f'{m}.delta_pct']}" for m in METRIC_PROSE)
    totals = ", ".join(f"{METRIC_PROSE[m]} from {d[f'{m}.baseline']} to {d[f'{m}.placed']}"
                       for m in METRIC_PROSE)
    explanation = (
        f"On the {b} basis, compared with running on arrival, the change is {deltas} "
        f"(positive means less, negative means more). "
        f"Per {d['energy_mwh']} on the {b} basis, that is {totals}. "
        f"The job was placed to minimise {obj}, shifted {d['shift_h']} within a "
        f"{d['window_h']} window.")
    fields = ["basis", "objective", "arrival.hour", "placed.hour", "shift_h", "window_h",
              "energy_mwh", "tradeoff"] + [f"{m}.{k}" for m in METRIC_PROSE
                                           for k in ("delta_pct", "baseline", "placed")]
    return Explanation(headline, explanation, fields, fallback=True)


def explain(record: PlacementRecord, model: ModelFn | None = None) -> Explanation:
    """Explain one placement: prompt, call, validate, verify, else ``fallback``. Never raises."""
    from thirst.verify import verify     # verify imports this module

    try:
        data = parse_response((model or nemotron())(build_prompt(record)))
    except Exception as e:                                   # noqa: BLE001 -- never raise
        return replace(fallback(record), error=f"{type(e).__name__}: {e}")
    return verify(record, Explanation(data["headline"], data["explanation"],
                                      data["fields_used"]))

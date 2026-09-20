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
    mode: str = "contiguous"      # "contiguous": one block; "split": the cheapest hours
    hours: tuple[int, ...] = ()   # hour offsets from arrival that the job runs in, sorted


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
the maths, and the reader already sees every figure in a chart next to your text. Your
job is to say what the figures MEAN, in words.

RECORD (field path -> the exact string you may print):
{display}

FACTS (computed by Python from the deltas; restate them, never re-derive them):
  better than running on arrival: {better}
  worse than running on arrival: {worse}
  unchanged: {same}
  objective, in words: {objective}

What the fields mean:
- The job arrived at arrival.hour. It may wait up to window_h (its slack) and can only
  move LATER, never earlier. placed.hour, shift_h after arrival, is the best hour in that
  window for `objective`. A shift_h of "0 h" means running on arrival was already best.
- mode says whether the job runs as one block from placed.hour, or is paused and resumed
  so it runs only in the cheapest separate hours{days}.
- For carbon, withdrawal and consumption, delta_pct is how much LESS than running on
  arrival: positive = better, negative = worse.
- tradeoff: "aligned" = at least one metric improves and none gets worse; "conflict" =
  at least one improves and at least one gets worse; "neutral" = no metric changes.
- Water withdrawal and water consumption are different metrics. Never combine them or
  call either one just "water".

Write it like this:
- headline: one sentence that states the FACTS in words and contains NO carbon,
  withdrawal or consumption figure. Times from the RECORD are fine. Name exactly the
  metrics in each FACTS list; say "both water metrics" only when water withdrawal and
  water consumption are in the same list.
  Shape: "Delaying to <placed.hour> improves <better> but worsens <worse>." (drop the
  "but" part when nothing is worse).
- explanation: two or three sentences.
  * First, WHY: how long the job waits (shift_h) out of the slack it had (window_h), and
    that placed.hour is the best hour in that window for the objective.
    When mode says the job is split, say that instead: it runs in those separate hours,
    the cheapest in the window, starting at placed.hour -- and the headline says it is
    split rather than naming one start time.
  * Then ONE sentence containing ONE figure: the objective's delta_pct. That sentence
    names the "{basis} basis"; it is the only place the basis is named.
- If shift_h is "0 h", instead: headline "Running at <arrival.hour> is already the best
  hour in the window."; explanation two sentences with no carbon, withdrawal or
  consumption figure: the job could wait up to <window_h>, but <arrival.hour> was already
  the best hour for the objective, so waiting would not help.
  * If anything is worse, say which metrics in words, with no figure.
  * No other carbon, withdrawal or consumption figures: do not list the deltas.
- Write the figure sentence in this frame, where the sign alone carries the direction:
  "On the {basis} basis, <metric> is <delta_pct> against running on arrival."
  Copy the sign: "+8.9 %", never "8.9 %". Never put "less", "more", "lower", "higher",
  "decreased by" or "increased by" next to a figure; the sign already says it.
- Talk about the job and the hours, not the machinery: do not mention Python, the
  RECORD, field names, or the words "aligned", "conflict", "neutral" or "tradeoff".

Rules (output that breaks any rule is thrown away):
1. Every number you write must be one of the RECORD strings above, copied character for
   character, including its "+" or "-" sign and units ("+9.9 %", "8 PM", "1 h"). Never
   write a quantity as a word ("one hour", "twice", "half"); use the RECORD string.
   Do not round, convert units, subtract, compare sizes, rank or count.
2. A sentence that states a carbon, withdrawal or consumption figure must contain the
   words "{basis} basis". Never mention any other accounting basis.
3. Use only the RECORD. Say nothing about fuels, power plants, cooling, PJM, weather or
   anything else that is not a field above.
4. fields_used: only field paths spelled exactly as the RECORD above prints them, e.g.
   "withdrawal.delta_pct" (never "water_withdrawal.delta_pct", which is the objective's
   name, not a field). The FACTS lines are not fields: never list them.

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
    # Direction per metric, on the same one-decimal values that are displayed (as
    # place._tradeoff does), so the words can never contradict the printed signs.
    sign = {m: round(getattr(record, m).delta_pct, 1) for m in METRIC_PROSE}
    facts = {k: ", ".join(METRIC_PROSE[m] for m in METRIC_PROSE if test(sign[m])) or "none"
             for k, test in (("better", lambda v: v > 0), ("worse", lambda v: v < 0),
                             ("same", lambda v: v == 0))}
    n_days = len({(record.arrival["hour"] - 1 + off) // 24 for off in record.hours})
    facts["days"] = (f", spread over {n_days} day{'s' if n_days != 1 else ''}"
                     if record.mode == "split" else "")
    return PROMPT.format(display=display, basis=BASIS_PROSE[record.basis],
                         objective=OBJECTIVE_PROSE[record.objective], **facts)


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
    better = [METRIC_PROSE[m] for m in METRIC_PROSE if round(getattr(record, m).delta_pct, 1) > 0]

    if record.placed == record.arrival:
        headline = f"The best start in the window is the arrival hour, {arr}, so the job stays put."
    elif record.tradeoff == "conflict":
        # Name what improved, not the objective: the objective can round to +0.0 %.
        headline = (f"Starting at {new} instead of {arr} lowers {' and '.join(better)} but makes "
                    f"{' and '.join(worse)} worse ({b} basis).")
    elif record.tradeoff == "aligned":
        listed = " and ".join(better) if len(better) < 3 else f"{', '.join(better[:-1])} and {better[-1]}"
        headline = (f"Starting at {new} instead of {arr} lowers {listed}"
                    f"{'' if len(better) == 3 else ', and nothing gets worse'} ({b} basis).")
    else:
        headline = f"Starting at {new} instead of {arr} changes no metric ({b} basis)."

    deltas = ", ".join(f"{METRIC_PROSE[m]} {d[f'{m}.delta_pct']}" for m in METRIC_PROSE)
    totals = ", ".join(f"{METRIC_PROSE[m]} from {d[f'{m}.baseline']} to {d[f'{m}.placed']}"
                       for m in METRIC_PROSE)
    how = (f"It runs in {len(record.hours)} separate hours, the cheapest in the window, "
           f"rather than as one block. " if record.mode == "split" else "")
    explanation = (
        f"{how}On the {b} basis, compared with running on arrival, the change is {deltas} "
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

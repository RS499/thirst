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

import re
from dataclasses import dataclass, replace

from thirst.classify import Classification
from thirst.explain import Explanation, PlacementRecord, fallback

METRICS = ("carbon", "consumption", "withdrawal")

# A clock time is one token ("05:00", never "5"). Otherwise an optional sign, digits
# with optional thousands commas, optional decimals. The lookbehind skips digits inside
# words and hashes ("CO2e", "28aecf4" -> "28"), identically for model text and display.
_TOKEN = re.compile(r"(?<![\w.,:])(?:\d{1,2}:\d{2}(?!\d)|[+\-−]?\s*\d[\d,]*(?:\.\d+)?)")
_BASIS_RE = {"average": re.compile(r"\baverage\b", re.I),
             "marginal_empirical": re.compile(r"\bmarginal[-_ ]empirical\b", re.I)}
# Outside facts the record never contains. Allowed only if a display string has the word.
_OUTSIDE = re.compile(r"\b(nuclear|coal|gas|oil|solar|wind|hydro\w*|renewables?|fossil|"
                      r"cooling|reactors?|turbines?|plants?|pjm|weather|temperature|heat|"
                      r"demand|peak|off-peak)\b", re.I)


@dataclass(frozen=True)
class Violation:
    rule: str                     # "uncomputed_number" | "basis_missing" | "unknown_field" | ...
    detail: str


def _norm(token: str) -> str:
    """Drop whitespace, commas and "%"; map the unicode minus to ASCII. Keeps the sign."""
    return re.sub(r"[\s,%]", "", token).replace("−", "-")


def _sentences(text: str) -> list[str]:
    # Not after "vs." / "e.g." / "i.e.", which end in a period mid-sentence.
    return [s for s in re.split(r"(?<!\bvs\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<=[.!?])\s+",
                                text.strip()) if s]


def extract_numbers(text: str) -> list[str]:
    """Return every numeric token in ``text`` (integers, decimals, percents, signs)."""
    return [_norm(m.group(0)) for m in _TOKEN.finditer(text)]


def allowed_numbers(record: PlacementRecord) -> set[str]:
    """Normalised set of numeric tokens the explainer may print for ``record``."""
    return {t for v in record.display.values() for t in extract_numbers(v)}


def _metric_numbers(record: PlacementRecord) -> set[str]:
    """Tokens that are savings/total figures, so their sentence must name the basis."""
    return {t for k, v in record.display.items()
            if k.split(".")[0] in METRICS for t in extract_numbers(v)}


def _resolves(record: PlacementRecord, path: str) -> bool:
    if path in record.display:
        return True
    obj = record
    for part in path.split("."):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        elif not isinstance(obj, dict) and hasattr(obj, part) and not part.startswith("_"):
            obj = getattr(obj, part)
        else:
            return False
    return True


def verify_classification(description: str, result: Classification) -> list[Violation]:
    """Check ``window_phrase`` is a verbatim substring and ``rationale`` has no digits."""
    out = []
    if result.window_phrase is not None and result.window_phrase not in description:
        out.append(Violation("phrase_not_verbatim", result.window_phrase))
    if re.search(r"\d", result.rationale):
        out.append(Violation("digit_in_rationale", result.rationale))
    return out


def verify_explanation(record: PlacementRecord, result: Explanation) -> list[Violation]:
    """Apply both project rules plus a ``fields_used`` existence check.

    A number passes only if its normalised token, sign included, is a display token:
    "1.4" does not match "-1.4" or "+1.4", since those are opposite or unsigned claims.
    """
    allowed, metric = allowed_numbers(record), _metric_numbers(record)
    own = _BASIS_RE[record.basis]
    other = [r for b, r in _BASIS_RE.items() if b != record.basis]
    display_text = " ".join(record.display.values()).lower()
    out: list[Violation] = []

    for part, text in (("headline", result.headline), ("explanation", result.explanation)):
        for tok in extract_numbers(text):
            if tok in allowed:
                continue
            bare = tok.lstrip("+-")
            flipped = [a for a in allowed if a.lstrip("+-") == bare]
            rule = "sign_mismatch" if flipped else "uncomputed_number"
            out.append(Violation(rule, f"{part}: {tok!r}"
                                 + (f" (record has {', '.join(sorted(flipped))})" if flipped else "")))
        for s in _sentences(text):
            if metric & set(extract_numbers(s)) and not own.search(s):
                out.append(Violation("basis_missing", f"{part}: {s!r}"))
        for r in other:
            if r.search(text):
                out.append(Violation("basis_mismatch", f"{part} names another basis"))
        for m in _OUTSIDE.finditer(text):
            if m.group(0).lower() not in display_text:
                out.append(Violation("outside_fact", f"{part}: {m.group(0)!r}"))

    if len(_sentences(result.headline)) != 1:
        out.append(Violation("sentence_count", "headline must be one sentence"))
    if not 2 <= len(_sentences(result.explanation)) <= 4:
        out.append(Violation("sentence_count", "explanation must be two to four sentences"))
    for f in result.fields_used:
        if not _resolves(record, f):
            out.append(Violation("unknown_field", f))
    return out


def verify(record: PlacementRecord, result: Explanation) -> Explanation:
    """Return ``result`` if it has no violations, else ``explain.fallback(record)``."""
    violations = verify_explanation(record, result)
    if not violations:
        return result
    return replace(fallback(record),
                   error="; ".join(f"{v.rule}: {v.detail}" for v in violations))

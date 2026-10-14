"""Grounded narration: explanations are rendered from a deterministic evidence object, never invented. Owner: D.

Rule (what-if planner and bottleneck analyzer):
    1. The engine builds an EVIDENCE object (plain JSON: counterfactual runs, shadow prices, graph analysis, Monte Carlo)
       including preformatted display strings for every figure a sentence may quote.
    2. A deterministic TEMPLATE renders every section from the evidence alone (always available).
    3. An LLM may only re-word the template sections. Its output is accepted only if every number in it exists in the
       evidence (`ungrounded`); otherwise, or with no API key / any API error, the template is used. The reason a
       narrative was rejected is returned so the UI can say which text it shows.

Number matching (`ungrounded`): every number written in the text must equal a number that appears anywhere in the
evidence JSON (including inside its display strings) after rounding that evidence number to the number of decimals
written, or be within ROUND_TOL relative of it (e.g. "1.2 L" for INR 1,23,456 is matched through the display
string "₹1.2 L" the evidence carries). Thousands separators are ignored and magnitudes are compared (a hyphen in
"days 2-5" is a range, not a sign). Digits glued to letters are identifiers (S2, F1->W3, v1), not numbers.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

ROUND_TOL = 1e-6
_NUM = re.compile(r"(?<![A-Za-z0-9_.])\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> list[tuple[float, int]]:
    """[(value, decimals written)] for every number in `text` (IDs like "S2" or "F1->W3" are not numbers)."""
    out = []
    for m in _NUM.findall(text):
        raw = m.replace(",", "")
        try:
            out.append((float(raw), len(raw.split(".")[1]) if "." in raw else 0))
        except ValueError:
            continue
    return out


def evidence_numbers(evidence: Any) -> list[float]:
    return sorted({v for v, _ in numbers(json.dumps(evidence, default=str, ensure_ascii=False))})


def _grounded(value: float, decimals: int, allowed: list[float]) -> bool:
    for a in allowed:
        if abs(a - value) <= ROUND_TOL * max(1.0, a) or round(a, decimals) == value:
            return True
    return False


def ungrounded(texts: list[str], evidence: Any) -> list[float]:
    """Numbers in `texts` that do not exist in `evidence` (empty list = fully grounded)."""
    allowed = evidence_numbers(evidence)
    bad = []
    for t in texts:
        for v, d in numbers(t):
            if not _grounded(v, d, allowed):
                bad.append(v)
    return bad


def section_texts(sections: list[dict]) -> list[str]:
    out = []
    for s in sections:
        out.append(s.get("title", ""))
        out.extend(s.get("paragraphs", []))
        out.extend(s.get("bullets", []))
        for item in s.get("items", []):
            out.append(item.get("text", "") if isinstance(item, dict) else str(item))
    return out


def narrate(evidence: dict, template: list[dict], narrator: Callable[[dict, list[dict]], list[dict]] | None = None) -> dict:
    """{sections, source: "llm" | "template", rejected: reason | None}. The template is validated too (a bug there
    must surface in tests, not reach a user)."""
    rejected = None
    if narrator is not None:
        try:
            candidate = narrator(evidence, template)
            if [s.get("key") for s in candidate] != [s.get("key") for s in template]:
                raise ValueError("narrator changed the section structure")
            bad = ungrounded(section_texts(candidate), evidence)
            if bad:
                raise ValueError(f"narrative used numbers that are not in the evidence: {bad[:5]}")
            # keep the evidence attached to each section; the narrator only rewrites text
            merged = [{**t, **{k: c[k] for k in ("paragraphs", "bullets") if k in c}} for t, c in zip(template, candidate)]
            return {"sections": merged, "source": "llm", "rejected": None}
        except Exception as exc:  # noqa: BLE001 - no key, API error, bad JSON or ungrounded numbers: use the template
            # no API key is not a rejection: the LLM simply is not configured
            not_configured = type(exc).__name__ == "LLMUnavailable" and "not set" in str(exc)
            rejected = None if not_configured else str(exc)[:300]
    bad = ungrounded(section_texts(template), evidence)
    return {"sections": template, "source": "template", "rejected": rejected,
            "template_ungrounded": bad or None}

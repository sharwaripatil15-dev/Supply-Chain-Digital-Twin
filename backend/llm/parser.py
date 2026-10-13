"""LLM helpers: scenario PARSING and playbook NARRATION only. Owner: D.

Rule: the LLM never computes numbers.
  * parse_scenario turns plain English into structured events (JSON via structured outputs), which are then
    validated against the real graph (ids exist, edges exist, demand targets are retailers or customers, severity 0..1).
  * write_playbook rewords numbers the engine already computed into a 5-step plan. Every number in its output
    (other than the "Day N:" step labels) must equal a number in the engine output it was given, or the
    playbook is rejected and the caller uses the deterministic template instead.
Failures raise LLMUnavailable / ScenarioParseError with a message meant for the UI, which then falls back to
the event builder dropdowns (parse) or the template playbook (narration). A missing API key is not an error state
for the app: it just means those fallbacks are used.
"""
from __future__ import annotations

import json
import re
from typing import Any

import networkx as nx
from pydantic import BaseModel, ValidationError

from config import settings
from core.graph import node_index
from schemas import Event
from validation import validate_events

FALLBACK_HINT = "Use the event builder below instead."
PLAYBOOK_STEPS = 5


class LLMUnavailable(RuntimeError):
    """No API key configured, the API failed, or the model declined. Message is shown in the UI."""


class ScenarioParseError(ValueError):
    """The model answered, but the text could not be mapped to valid events. Message is shown in the UI."""


class _ParsedScenario(BaseModel):
    events: list[Event]


class _Playbook(BaseModel):
    steps: list[str]


def _client():
    if not settings.anthropic_api_key:
        raise LLMUnavailable(f"Plain-English parsing is off: ANTHROPIC_API_KEY is not set. {FALLBACK_HINT}")
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _call(**kwargs):
    """messages.parse with API errors translated into LLMUnavailable (most specific first)."""
    import anthropic

    try:
        response = _client().messages.parse(model=settings.anthropic_model, max_tokens=16000, **kwargs)
    except LLMUnavailable:
        raise
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable(f"The Anthropic API rejected the key. {FALLBACK_HINT}") from exc
    except anthropic.RateLimitError as exc:
        raise LLMUnavailable(f"The Anthropic API is rate limiting requests; try again shortly. {FALLBACK_HINT}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable(f"Cannot reach the Anthropic API. {FALLBACK_HINT}") from exc
    except anthropic.APIStatusError as exc:
        raise LLMUnavailable(f"The Anthropic API returned an error ({exc.status_code}). {FALLBACK_HINT}") from exc
    except ValidationError as exc:  # structured output did not match the schema
        raise LLMUnavailable(f"The model's answer was not valid JSON for this schema. {FALLBACK_HINT}") from exc
    if response.stop_reason == "refusal":
        raise LLMUnavailable(f"The model declined this request. {FALLBACK_HINT}")
    if response.parsed_output is None:
        raise LLMUnavailable(f"The model returned no structured answer (stop_reason={response.stop_reason}). {FALLBACK_HINT}")
    return response.parsed_output


def _network_brief(G: nx.DiGraph) -> str:
    nodes = "\n".join(f"- {n}: {d['kind']}, {d.get('name', '')}, {d.get('city', '')}" for n, d in G.nodes(data=True))
    edges = ", ".join(f"{u}->{v}" for u, v in G.edges())
    return f"Nodes:\n{nodes}\nLanes: {edges}"


def parse_scenario(text: str, G: nx.DiGraph, horizon: int = 30) -> list[Event]:
    """Plain-English disruption description -> validated list[Event].

    Raises LLMUnavailable (no key / API failure / refusal) or ScenarioParseError (nothing usable, or invalid ids).
    """
    system = (
        "You convert supply-chain disruption descriptions into structured events for a simulator. Output JSON only.\n"
        "Event types: 'node' (a site is out or degraded; target = node id), 'edge' (a lane is blocked; target = "
        "'SRC->DST' using a lane from the list), 'demand' (demand spike at a retailer or customer; target = that node's id).\n"
        f"Day 0 is today; the simulation covers days 0-{horizon - 1}. start = first affected day, duration in days, "
        "severity in 0..1 (1 = total outage, or +100% demand). If no timing is given, use start=1, duration=7.\n"
        "Map places to the ids below by city or name. Use only ids and lanes from these lists. If the text does not "
        "describe a disruption to this network, return an empty events list.\n\n" + _network_brief(G)
    )
    parsed = _call(system=system, messages=[{"role": "user", "content": text}], output_format=_ParsedScenario)
    if not parsed.events:
        raise ScenarioParseError(f"Couldn't find a disruption to this network in that text. {FALLBACK_HINT}")
    nodes, edges = node_index(G)
    try:
        return validate_events(parsed.events, nodes, edges)
    except ValueError as exc:
        raise ScenarioParseError(f"The parsed events don't match the network ({exc}). {FALLBACK_HINT}") from exc


_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_DAY_LABEL = re.compile(r"^\s*Day\s+\d+\s*:")


def _numbers(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in _NUM.findall(text)]


def ungrounded_numbers(steps: list[str], facts: Any) -> list[float]:
    """Numbers in `steps` (ignoring "Day N:" labels) that do not appear in `facts`."""
    allowed = set(_numbers(json.dumps(facts, default=str, ensure_ascii=False)))
    bad = []
    for step in steps:
        for v in _numbers(_DAY_LABEL.sub("", step)):
            if not any(abs(v - a) <= 1e-6 * max(1.0, abs(a)) for a in allowed):
                bad.append(v)
    return bad


def write_playbook(facts: dict[str, Any]) -> list[str]:
    """Narrate engine output as exactly PLAYBOOK_STEPS action steps, using only numbers present in `facts`.

    Raises LLMUnavailable if the model is unavailable, returns the wrong number of steps, or uses any number that
    is not in `facts`; the caller then falls back to the deterministic template playbook.
    """
    system = (
        f"Write an operations playbook of exactly {PLAYBOOK_STEPS} steps for a supply-chain manager, as JSON. Each "
        "step starts with 'Day N:' using a day that appears in the facts, then one concrete action.\n"
        "Use ONLY the facts in the JSON provided. Do not calculate, estimate, round, convert or invent any number: "
        "copy numbers exactly as they appear (including the preformatted *_display strings), or leave them out."
    )
    facts_json = json.dumps(facts, default=str, ensure_ascii=False)
    parsed = _call(system=system, messages=[{"role": "user", "content": facts_json}], output_format=_Playbook)
    steps = [s.strip() for s in parsed.steps if s.strip()]
    if len(steps) != PLAYBOOK_STEPS:
        raise LLMUnavailable(f"Narrator returned {len(steps)} steps instead of {PLAYBOOK_STEPS}.")
    invented = ungrounded_numbers(steps, facts)
    if invented:
        raise LLMUnavailable(f"Narrator used numbers not produced by the engine: {invented[:5]}")
    return steps

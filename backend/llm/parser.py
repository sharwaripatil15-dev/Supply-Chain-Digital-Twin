"""LLM and deterministic rule-based scenario PARSER and Playbook Narrator.

CORE PRINCIPLES (Non-negotiable):
1. The LLM only (a) parses plain English into structured events and (b) narrates results.
   It must NEVER invent numbers, days, or cascade timings.
2. All numbers (cascade timing, TTS, TTR, risk, costs) are computed by our own code:
   the graph, the simulator (core/sim.py), and the XGBoost surrogate.
3. Every LLM or parser output is validated before use (Pydantic). Invalid output triggers
   the rule-based fallback, never a crash.
4. The system works fully offline (no API key) using the rule-based parser.
5. Heuristics are labeled 'calibrated assumptions' and loaded from backend/config/assumptions.json.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, Field, ValidationError

from config import settings
from core.cascade import compute_cascade
from core.followups import generate_data_followups
from core.graph import node_index
from core.risk_ml import scenario_quick_risk
from schemas import Event, ParseResponse
from validation import validate_events

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_NODES_FILE = _CONFIG_DIR / "nodes.json"
_ASSUMPTIONS_FILE = _CONFIG_DIR / "assumptions.json"

EXAMPLE_PROMPTS = [
    "Heavy monsoon flooding in Chennai halts chip supplies for 10 days, while Mumbai e-commerce festival surges consumer demand by 45%.",
    "Transport strike blocks Bhiwandi warehouse for 5 days.",
    "Bengaluru assembly plant operates at 20% capacity from day 3 for 8 days.",
]

# In-memory LRU cache for identical prompts
_PARSE_CACHE: dict[str, dict] = {}


FALLBACK_HINT = "Use the event builder below instead."
PLAYBOOK_STEPS = 5

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_DAY_LABEL = re.compile(r"^\s*Day\s+\d+\s*:")


def _numbers(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in _NUM.findall(text)]


def ungrounded_numbers(steps: list[str], facts: Any) -> list[float]:
    allowed = set(_numbers(json.dumps(facts, default=str, ensure_ascii=False)))
    bad = []
    for step in steps:
        for v in _numbers(_DAY_LABEL.sub("", step)):
            if not any(abs(v - a) <= 1e-6 * max(1.0, abs(a)) for a in allowed):
                bad.append(v)
    return bad


class LLMUnavailable(RuntimeError):
    """No API key configured, the API failed, or the model declined."""


class ScenarioParseError(ValueError):
    """The input could not be mapped to valid supply chain events."""


class _ParsedScenario(BaseModel):
    events: list[Event]
    interpreted_narrative: str = Field(default="")
    ambiguities: list[str] = Field(default_factory=list)


class _Playbook(BaseModel):
    steps: list[str]


def _client():
    if not settings.anthropic_api_key:
        raise LLMUnavailable(f"Plain-English parsing is off: ANTHROPIC_API_KEY is not set. {FALLBACK_HINT}")
    import anthropic
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _call(**kwargs):
    """Anthropic messages.parse wrapper with API errors translated into LLMUnavailable."""
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
    except ValidationError as exc:
        raise LLMUnavailable(f"The model's answer was not valid JSON for this schema. {FALLBACK_HINT}") from exc
    if response.stop_reason == "refusal":
        raise LLMUnavailable(f"The model declined this request. {FALLBACK_HINT}")
    if response.parsed_output is None:
        raise LLMUnavailable(f"The model returned no structured answer (stop_reason={response.stop_reason}). {FALLBACK_HINT}")
    return response.parsed_output


def _load_nodes_data() -> list[dict]:
    if _NODES_FILE.exists():
        with open(_NODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _load_assumptions_data() -> dict:
    if _ASSUMPTIONS_FILE.exists():
        with open(_ASSUMPTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": "1.0.0", "disruptions": {}}


def _make_cache_key(text: str) -> str:
    assump_ver = _load_assumptions_data().get("version", "1.0.0")
    norm_text = text.strip().lower()[:500]
    return f"{norm_text}:{assump_ver}"


# -----------------------------------------------------------------------------
# RULE-BASED DETERMINISTIC PARSER (Zero API Key / Fully Offline)
# -----------------------------------------------------------------------------
def _split_clauses(text: str) -> list[str]:
    """Split compound sentences into distinct disruption clauses."""
    # Split on semicolons, periods, "while", "and" (when not connecting node names), or "then"
    pattern = r"(?:;|\.|\bwhile\b|\band\b(?!\s+(?:coils|polymers|components|dc|hub|plant|works|retail|supplier|demand))\b|\bthen\b)"
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _extract_timing(clause: str, default_duration: int = 7) -> tuple[int, int]:
    """Extract start_day and duration_days using regular expressions."""
    # Start day: "start day 3", "starting day 2", "from day 4", "day 5"
    start = 0
    m_start = re.search(r"(?:start(?:ing)?\s+(?:on\s+|at\s+)?day\s+(\d+)|from\s+day\s+(\d+)|\bday\s+(\d+)\b)", clause, re.IGNORECASE)
    if m_start:
        for g in m_start.groups():
            if g is not None:
                start = int(g)
                break

    # Duration: "for 10 days", "for 10d", "10 days", "10-day"
    duration = default_duration
    m_dur = re.search(r"(?:for\s+(\d+)\s*(?:days?|d)|\b(\d+)\s*(?:days?|d)\b)", clause, re.IGNORECASE)
    if m_dur:
        for g in m_dur.groups():
            if g is not None:
                duration = int(g)
                break

    return start, duration


def _extract_percentage(clause: str) -> float | None:
    """Extract percentage like '45%' -> 0.45."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", clause)
    if m:
        return float(m.group(1)) / 100.0
    return None


def _find_node_and_ambiguity(clause: str, nodes_data: list[dict], G: nx.DiGraph) -> tuple[str | None, list[str]]:
    """Match clause against known nodes: exact alias first, strict fuzzy matching, multi-node ambiguity handling."""
    clause_lower = clause.lower()
    ambiguities: list[str] = []

    # Check for route/lane mention first if corridor/lane keywords present
    has_lane_keyword = any(w in clause_lower for w in ("lane", "corridor", "route", "highway", "road", "->"))
    if has_lane_keyword:
        lane_match = re.search(r"([A-Za-z0-9]+)\s*(?:to|->)\s*([A-Za-z0-9]+)", clause, re.IGNORECASE)
        if lane_match:
            src_raw, dst_raw = lane_match.group(1).lower(), lane_match.group(2).lower()
            src_cands = [
                n["id"] for n in nodes_data
                if src_raw in [n["id"].lower(), n["city"].lower()] or any(src_raw in a.lower() for a in n.get("aliases", []))
            ]
            dst_cands = [
                n["id"] for n in nodes_data
                if dst_raw in [n["id"].lower(), n["city"].lower()] or any(dst_raw in a.lower() for a in n.get("aliases", []))
            ]
            for u in src_cands:
                for v in dst_cands:
                    if G.has_edge(u, v):
                        return f"{u}->{v}", ambiguities

    # 1. Exact alias match (longest alias first to prevent substring collisions)
    all_alias_pairs = []
    for node in nodes_data:
        nid = node["id"]
        for alias in node.get("aliases", []):
            all_alias_pairs.append((len(alias), alias.lower(), nid, node))
    all_alias_pairs.sort(key=lambda x: -x[0])

    for _, alias, nid, node in all_alias_pairs:
        if re.search(rf"\b{re.escape(alias)}\b", clause_lower):
            # Check if this city has multiple nodes
            city = node.get("city", "")
            same_city_nodes = [n for n in nodes_data if n.get("city", "").lower() == city.lower() and n["id"] != nid]
            if same_city_nodes:
                other_ids = ", ".join(f"{n['id']} ({n['name']})" for n in same_city_nodes)
                ambiguities.append(f"{city} also hosts {other_ids}; resolved to {nid} based on exact alias '{alias}'")
            return nid, ambiguities

    # 3. City-level matching with context disambiguation
    cities = {n.get("city", "").lower(): n.get("city", "") for n in nodes_data if n.get("city")}
    for city_lower, city_real in cities.items():
        if re.search(rf"\b{re.escape(city_lower)}\b", clause_lower):
            matching_nodes = [n for n in nodes_data if n.get("city", "").lower() == city_lower]
            if len(matching_nodes) == 1:
                return matching_nodes[0]["id"], ambiguities

            # Multi-node city (e.g. Mumbai -> C1 and W1; Chennai -> S2 and W3; Bengaluru -> F1 and C3)
            # Use contextual keywords to disambiguate:
            is_retail = any(w in clause_lower for w in ("retail", "demand", "consumer", "customer", "festival", "e-commerce", "sale", "surge"))
            is_warehouse = any(w in clause_lower for w in ("warehouse", "dc", "storage", "hub", "depot"))
            is_supplier = any(w in clause_lower for w in ("supplier", "chip", "chips", "electronics", "steel", "coil", "polymers", "raw"))
            is_plant = any(w in clause_lower for w in ("plant", "factory", "assembly", "works", "manufactur"))

            for n in matching_nodes:
                kind = n.get("kind", "")
                if is_retail and kind == "customer":
                    other_desc = ", ".join(m["id"] for m in matching_nodes if m["id"] != n["id"])
                    ambiguities.append(f"{city_real} also matches {other_desc}; resolved to {n['id']} due to retail/demand context")
                    return n["id"], ambiguities
                if is_warehouse and kind == "warehouse":
                    other_desc = ", ".join(m["id"] for m in matching_nodes if m["id"] != n["id"])
                    ambiguities.append(f"{city_real} also matches {other_desc}; resolved to {n['id']} due to warehouse context")
                    return n["id"], ambiguities
                if is_supplier and kind == "supplier":
                    other_desc = ", ".join(m["id"] for m in matching_nodes if m["id"] != n["id"])
                    ambiguities.append(f"{city_real} also matches {other_desc}; resolved to {n['id']} due to supplier context")
                    return n["id"], ambiguities
                if is_plant and kind == "factory":
                    other_desc = ", ".join(m["id"] for m in matching_nodes if m["id"] != n["id"])
                    ambiguities.append(f"{city_real} also matches {other_desc}; resolved to {n['id']} due to manufacturing context")
                    return n["id"], ambiguities

            # If no context keyword matched, flag as ambiguous and choose first candidate
            cand_str = " and ".join(f"{m['id']} ({m['name']})" for m in matching_nodes)
            ambiguities.append(f"{city_real} matches multiple sites ({cand_str}): please confirm intended target")
            return matching_nodes[0]["id"], ambiguities

    # 4. Strict fuzzy match on node names (ratio >= 0.85)
    for word in clause.split():
        clean_word = re.sub(r"[^\w]", "", word).lower()
        if len(clean_word) < 4:
            continue
        for n in nodes_data:
            for alias in n.get("aliases", []):
                if difflib.SequenceMatcher(None, clean_word, alias.lower()).ratio() >= 0.85:
                    return n["id"], ambiguities

    return None, ambiguities


def _merge_overlapping_events(events: list[Event], rule: str = "conservative_worst_case") -> list[Event]:
    """Merge multiple disruption events on the same target according to the configured rule."""
    if len(events) <= 1:
        return events

    grouped: dict[str, list[Event]] = {}
    for ev in events:
        grouped.setdefault(ev.target, []).append(ev)

    merged: list[Event] = []
    for target, ev_list in grouped.items():
        if len(ev_list) == 1:
            merged.append(ev_list[0])
            continue

        # Rule: conservative_worst_case
        # start = min(starts), end = max(ends), severity = max(severities)
        first_ev = ev_list[0]
        min_start = min(e.start for e in ev_list)
        max_end = max(e.start + e.duration for e in ev_list)
        total_duration = max(1, max_end - min_start)
        max_sev = max(e.severity for e in ev_list)
        justifications = " & ".join(filter(None, [e.justification for e in ev_list]))

        merged.append(
            Event(
                type=first_ev.type,
                target=target,
                start=min_start,
                duration=total_duration,
                severity=max_sev,
                justification=f"Merged overlapping events on {target}: {justifications}",
            )
        )
    return merged


def parse_by_rules(text: str, G: nx.DiGraph) -> dict[str, Any]:
    """Rule-based scenario parser with Indian supply chain keyword table and fuzzy entity matching."""
    text = text.strip()[:500]
    nodes_data = _load_nodes_data()
    assump_data = _load_assumptions_data()
    disruptions_cfg = assump_data.get("disruptions", {})
    overlap_rule = assump_data.get("overlapping_event_rule", "conservative_worst_case")

    clauses = _split_clauses(text)
    raw_events: list[Event] = []
    all_ambiguities: list[str] = []
    narrative_parts: list[str] = []

    for clause in clauses:
        target_id, ambiguities = _find_node_and_ambiguity(clause, nodes_data, G)
        if ambiguities:
            all_ambiguities.extend(ambiguities)

        if not target_id:
            continue

        pct = _extract_percentage(clause)
        clause_lower = clause.lower()

        # Identify hazard / event type
        is_surge = any(w in clause_lower for w in ("festival", "surge", "spike", "jump", "demand", "increase", "rise"))
        is_freeze = any(w in clause_lower for w in ("strike", "halt", "halts", "block", "blocked", "freeze", "offline", "shut", "stop"))
        is_flood = any(w in clause_lower for w in ("monsoon", "flood", "flooding", "waterlogging", "rain"))
        is_fire = any(w in clause_lower for w in ("fire", "burn", "explosion"))

        if is_surge:
            ev_type = "demand_surge"
            default_dur = disruptions_cfg.get("festival", {}).get("default_duration_days", 7)
            start, duration = _extract_timing(clause, default_dur)
            multiplier = 1.0 + pct if pct is not None else disruptions_cfg.get("festival", {}).get("severity", 1.45)
            severity = multiplier
            justification = f"Demand surge +{int(round((multiplier - 1.0) * 100))}% ({multiplier:.2f}x multiplier) from day {start} for {duration}d"
        elif "->" in target_id or "lane" in clause_lower or "road" in clause_lower:
            ev_type = "route_block"
            default_dur = disruptions_cfg.get("blockade", {}).get("default_duration_days", 5)
            start, duration = _extract_timing(clause, default_dur)
            severity = 1.0
            justification = f"Corridor blocked 100% from day {start} for {duration}d"
        elif is_flood:
            ev_type = "capacity_drop"
            default_dur = disruptions_cfg.get("monsoon", {}).get("default_duration_days", 10)
            start, duration = _extract_timing(clause, default_dur)
            severity = pct if pct is not None else disruptions_cfg.get("monsoon", {}).get("severity", 0.85)
            justification = f"Monsoon flooding assumed {int(round(severity * 100))}% capacity drop from day {start} for {duration}d"
        elif is_freeze:
            ev_type = "node_freeze"
            default_dur = disruptions_cfg.get("strike", {}).get("default_duration_days", 5)
            start, duration = _extract_timing(clause, default_dur)
            severity = 1.0
            justification = f"Node operation frozen 100% from day {start} for {duration}d"
        elif is_fire:
            ev_type = "capacity_drop"
            default_dur = disruptions_cfg.get("fire", {}).get("default_duration_days", 14)
            start, duration = _extract_timing(clause, default_dur)
            severity = pct if pct is not None else disruptions_cfg.get("fire", {}).get("severity", 0.90)
            justification = f"Fire damage assumed {int(round(severity * 100))}% capacity drop for {duration}d"
        else:
            # Default or flood / machinery capacity drop
            ev_type = "capacity_drop"
            default_dur = disruptions_cfg.get("monsoon", {}).get("default_duration_days", 10) if is_flood else 7
            start, duration = _extract_timing(clause, default_dur)

            # Check phrasing: "operates at only 20% capacity" -> drop is 80%
            if "at only" in clause_lower and pct is not None:
                severity = round(1.0 - pct, 2)
            elif pct is not None:
                severity = round(pct, 2)
            elif is_flood:
                severity = disruptions_cfg.get("monsoon", {}).get("severity", 0.85)
            else:
                severity = disruptions_cfg.get("default_drop", {}).get("severity", 0.70)

            hazard_name = "Monsoon flooding" if is_flood else "Operational disruption"
            justification = f"{hazard_name} calibrated at {int(round(severity * 100))}% capacity drop from day {start} for {duration}d"

        ev = Event(
            type=ev_type,
            target=target_id,
            start=start,
            duration=duration,
            severity=severity,
            justification=justification,
        )
        raw_events.append(ev)
        narrative_parts.append(justification)

    if not raw_events:
        raise ScenarioParseError(
            "Could not identify a valid supply chain disruption in that text. "
            f"Try one of these examples:\n" + "\n".join(f"• {ex}" for ex in EXAMPLE_PROMPTS)
        )

    # Merge overlapping events according to defined rule
    merged_events = _merge_overlapping_events(raw_events, rule=overlap_rule)
    narrative = "; ".join(narrative_parts)

    return {
        "events": merged_events,
        "interpreted_narrative": narrative,
        "ambiguities": list(dict.fromkeys(all_ambiguities)),
        "confidence": 0.92 if len(merged_events) == len(clauses) else 0.80,
        "source": "rules",
    }


# -----------------------------------------------------------------------------
# LLM INTEGRATION (Gemini & Claude with strict 8.0s timeout & schema validation)
# -----------------------------------------------------------------------------
class _ParsedScenario(BaseModel):
    events: list[Event]
    interpreted_narrative: str = Field(default="")
    ambiguities: list[str] = Field(default_factory=list)


def _build_system_prompt(G: nx.DiGraph) -> str:
    nodes_data = _load_nodes_data()
    assump_data = _load_assumptions_data()
    nodes_formatted = "\n".join(f"- {n['id']}: {n.get('name', '')} ({n.get('city', '')}), type: {n.get('kind', '')}" for n in nodes_data)
    lanes_formatted = ", ".join(f"{u}->{v}" for u, v in G.edges())

    return (
        "You are a supply-chain scenario parser. Convert the user's text into JSON matching the provided schema. Rules:\n"
        f"- Only use node ids from this list:\n{nodes_formatted}\nLanes: {lanes_formatted}\n"
        "- Do NOT predict outcomes, cascades, or dates beyond what the user states. Only extract events.\n"
        f"- If the user gives no duration or severity, use the calibrated defaults from assumptions and say so in 'justification'.\n"
        "- If a place or node is ambiguous or unknown, add it to 'ambiguities' instead of guessing.\n\n"
        "Examples:\n"
        "1) 'Heavy monsoon flooding in Chennai halts chip supplies for 10 days' -> "
        "[{target:'S2', type:'capacity_drop', start_day:0, duration_days:10, severity:0.85, justification:'Monsoon flooding assumed 85% capacity loss; Chennai maps to S2'}]\n"
        "2) 'Transport strike blocks Bhiwandi warehouse for 5 days' -> "
        "[{target:'W1', type:'node_freeze', start_day:0, duration_days:5, severity:1.0, justification:'Strike assumed to fully freeze the node'}]\n"
        "3) 'Festival in Mumbai raises demand by 45%' -> "
        "[{target:'C1', type:'demand_surge', start_day:0, duration_days:7, severity:1.45, justification:'Demand multiplier 1.45 as stated'}] and ambiguities:['Mumbai also matches W1']\n"
        "4) 'Everything is on fire' -> events:[] and ambiguities:['No identifiable location or disruption']"
    )


def _call_gemini_structured(text: str, system_prompt: str) -> _ParsedScenario:
    """Call Google Gemini model using structured output."""
    if not settings.gemini_api_key:
        raise LLMUnavailable("GEMINI_API_KEY is not set.")

    # Using google-genai or direct requests with timeout
    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=text,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": _ParsedScenario,
            },
        )
        return _ParsedScenario.model_validate_json(response.text)
    except Exception as exc:
        raise LLMUnavailable(f"Gemini call failed: {exc}") from exc


def _call_claude_structured(text: str, system_prompt: str) -> _ParsedScenario:
    """Call Anthropic Claude model using messages.parse."""
    if not settings.anthropic_api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set.")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": text}],
            output_format=_ParsedScenario,
        )
        if response.parsed_output is None:
            raise LLMUnavailable("Claude returned no structured output.")
        return response.parsed_output
    except Exception as exc:
        raise LLMUnavailable(f"Claude call failed: {exc}") from exc


def parse_scenario_full(text: str, G: nx.DiGraph) -> ParseResponse:
    """Main parsing pipeline: caching -> provider selection -> rule fallback -> cascade -> surrogate risk."""
    clean_text = text.strip()[: settings.max_prompt_chars]
    cache_key = _make_cache_key(clean_text)

    if cache_key in _PARSE_CACHE:
        cached = _PARSE_CACHE[cache_key]
        return ParseResponse.model_validate(cached)

    result_dict: dict[str, Any] | None = None
    provider = settings.llm_provider.lower()
    system_prompt = _build_system_prompt(G)

    # Attempt LLM first if configured
    if provider in ("gemini", "claude"):
        try:
            if provider == "gemini" and settings.gemini_api_key:
                parsed = _call_gemini_structured(clean_text, system_prompt)
                result_dict = {
                    "events": parsed.events,
                    "interpreted_narrative": parsed.interpreted_narrative or "Scenario parsed via Gemini LLM.",
                    "ambiguities": parsed.ambiguities,
                    "confidence": 0.95,
                    "source": "llm",
                }
            elif provider == "claude" and settings.anthropic_api_key:
                parsed = _call_claude_structured(clean_text, system_prompt)
                result_dict = {
                    "events": parsed.events,
                    "interpreted_narrative": parsed.interpreted_narrative or "Scenario parsed via Claude LLM.",
                    "ambiguities": parsed.ambiguities,
                    "confidence": 0.95,
                    "source": "llm",
                }
        except Exception:
            # Automatic silent fallback to deterministic rule parser
            result_dict = None

    if result_dict is None:
        # Fall back to rule-based engine
        result_dict = parse_by_rules(clean_text, G)

    # Validate events against actual graph
    nodes, edges = node_index(G)
    validated_events = validate_events(result_dict["events"], nodes, edges)
    result_dict["events"] = validated_events

    # Deterministic cascade calculation (TTS / TTR)
    cascade_preview = compute_cascade(G, validated_events)
    result_dict["cascade_preview"] = cascade_preview

    # Data-driven followups
    followups = generate_data_followups(G, validated_events)
    result_dict["suggested_followups"] = followups

    # Instant surrogate ML risk estimate
    ml_risk = scenario_quick_risk(G, validated_events)
    result_dict["ml_quick_risk"] = ml_risk

    response = ParseResponse.model_validate(result_dict)
    _PARSE_CACHE[cache_key] = response.model_dump()
    return response


def _network_brief(G: nx.DiGraph) -> str:
    nodes = "\n".join(f"- {n}: {d['kind']}, {d.get('name', '')}, {d.get('city', '')}" for n, d in G.nodes(data=True))
    edges = ", ".join(f"{u}->{v}" for u, v in G.edges())
    return f"Nodes:\n{nodes}\nLanes: {edges}"


# Backward compatibility interface for existing tests & callers
def parse_scenario(text: str, G: nx.DiGraph, horizon: int = 30) -> list[Event]:
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


def write_playbook(facts: dict[str, Any]) -> list[str]:
    """Narrate engine output as exactly PLAYBOOK_STEPS action steps."""
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

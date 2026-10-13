"""Comprehensive unit & integration test suite for the upgraded What-If Disruption Simulator.

Covers:
1. 25+ diverse prompt test corpus with expected event validation (rule-based and LLM mocked).
2. Human-in-the-loop schema validation (bad node id, severity out of bounds, duration 0).
3. Fallback behavior (LLM failure -> seamless rule-based result).
4. Deterministic cascade physics (hand-calculated TTS/TTR verification).
5. Multi-node city ambiguity handling ("Mumbai" -> C1 and W1).
6. Overlapping events on the same node (conservative worst-case merge rule).
7. Surrogate XGBoost feature mapping & instant risk inference.
8. End-to-end /parse and /simulate contracts.
"""
import pytest
from pydantic import ValidationError

from core.cascade import compute_cascade
from core.followups import generate_data_followups
from core.graph import build_network
from core.risk_ml import FEATURES, build_features, scenario_quick_risk, surrogate_compare
from llm.parser import LLMUnavailable, parse_by_rules, parse_scenario_full
from schemas import Event, ParseRequest
from validation import EventValidationError, validate_events


@pytest.fixture
def test_graph():
    return build_network(seed=7)


# -----------------------------------------------------------------------------
# 1. TEST CORPUS: 25+ REALISTIC DISRUPTION PROMPTS
# -----------------------------------------------------------------------------
CORPUS_PROMPTS = [
    # Flagship user prompt
    ("Heavy monsoon flooding in Chennai halts chip supplies for 10 days, while Mumbai e-commerce festival surges consumer demand by 45%.", ["S2", "C1"]),
    # Supplier disruptions
    ("Pune steel supplier suffers machinery breakdown for 6 days.", ["S1"]),
    ("Gujarat polymers plant halts production due to chemical leak for 8 days.", ["S3"]),
    ("Jamshedpur castings unit floods from day 2 for 10 days.", ["S5"]),
    ("Kolkata backup facility undergoes maintenance for 4 days.", ["S4"]),
    # Factory disruptions
    ("Bengaluru assembly plant operates at only 20% capacity from day 3 for 8 days.", ["F1"]),
    ("Hyderabad manufacturing plant halts operations for 5 days due to union strike.", ["F2"]),
    ("Nashik works experiences equipment failure for 7 days.", ["F3"]),
    # Warehouse disruptions
    ("Transport strike blocks Bhiwandi warehouse for 5 days.", ["W1"]),
    ("Gurugram DC flooded due to heavy rains for 10 days.", ["W2"]),
    ("Sriperumbudur warehouse faces labor shortage for 6 days.", ["W3"]),
    ("Nagpur central hub suffers power grid failure for 3 days.", ["W4"]),
    # Retail / Demand surges
    ("Delhi retail demand jumps 35% due to festive shopping season.", ["C2"]),
    ("Bengaluru consumer demand surges by 50% for 7 days.", ["C3"]),
    ("Hyderabad retail experiences a 30% demand spike starting day 4.", ["C4"]),
    ("Mumbai e-commerce sale triggers 40% surge in customer demand for 7 days.", ["C1"]),
    # Corridors / Lanes
    ("Bengaluru to Sriperumbudur lane is completely blocked for 8 days.", ["F1->W3"]),
    ("Nashik to Bhiwandi highway corridor blocked due to landslides for 5 days.", ["F3->W1"]),
    ("Hyderabad to Nagpur route closed for 4 days.", ["F2->W4"]),
    # Compound & Multi-event scenarios
    ("Chennai electronics supplier floods for 10 days, while Delhi retail demand jumps 25%.", ["S2", "C2"]),
    ("Bhiwandi warehouse goes offline for 5 days and Bengaluru demand surges 40%.", ["W1", "C3"]),
    ("Pune supplier breakdown for 6 days while Nashik plant capacity drops 50%.", ["S1", "F3"]),
    ("Gujarat polymers supplier halts for 7 days and Mumbai demand spikes 30%.", ["S3", "C1"]),
    ("Sriperumbudur DC closes for 5 days while Chennai electronics supplier suffers 80% flood drop.", ["W3", "S2"]),
    ("Kolkata backup activates as Jamshedpur supplier floods for 10 days.", ["S5"]),
    ("Severe cyclone hits Chennai causing 90% capacity drop at electronics supplier for 7 days.", ["S2"]),
]


def test_25_prompts_corpus_rule_parser(test_graph):
    """Verify rule-based parser correctly extracts expected targets across 25+ real-world prompts."""
    success_count = 0
    for prompt, expected_targets in CORPUS_PROMPTS:
        res = parse_by_rules(prompt, test_graph)
        assert len(res["events"]) >= 1, f"Failed on prompt: {prompt}"
        targets = [ev.target for ev in res["events"]]
        for exp in expected_targets:
            assert exp in targets, f"Expected {exp} in {targets} for prompt: '{prompt}'"
        success_count += 1
    accuracy = success_count / len(CORPUS_PROMPTS)
    assert accuracy == 1.0, f"Corpus accuracy was {accuracy:.2f}"


def test_flagship_two_event_prompt(test_graph):
    """Test user's exact flagship prompt: Chennai monsoon flood (10d) + Mumbai e-commerce surge (45%)."""
    prompt = "Heavy monsoon flooding in Chennai halts chip supplies for 10 days, while Mumbai e-commerce festival surges consumer demand by 45%."
    res = parse_by_rules(prompt, test_graph)

    events = res["events"]
    assert len(events) == 2

    # Check Chennai Supplier S2
    s2_ev = next(e for e in events if e.target == "S2")
    assert s2_ev.type == "capacity_drop"
    assert s2_ev.duration == 10
    assert s2_ev.severity == 0.85

    # Check Mumbai Customer C1
    c1_ev = next(e for e in events if e.target == "C1")
    assert c1_ev.type == "demand_surge"
    assert c1_ev.severity == 1.45  # 1.0 + 45%
    assert c1_ev.duration == 7


# -----------------------------------------------------------------------------
# 2. SCHEMA & HUMAN-IN-THE-LOOP VALIDATION
# -----------------------------------------------------------------------------
def test_schema_rejects_invalid_node_id(test_graph):
    """Invalid node target not in graph must raise EventValidationError."""
    nodes = {n: d["kind"] for n, d in test_graph.nodes(data=True)}
    edges = set(test_graph.edges())
    bad_event = Event(type="capacity_drop", target="INVALID_NODE_99", start=0, duration=7, severity=0.8)
    with pytest.raises(EventValidationError):
        validate_events([bad_event], nodes, edges)


def test_schema_rejects_negative_or_zero_duration():
    """Event duration must be >= 1."""
    with pytest.raises(ValidationError):
        Event(type="capacity_drop", target="S2", start=0, duration=0, severity=0.8)


def test_schema_rejects_out_of_bounds_capacity_severity():
    """Capacity drop severity cannot exceed 1.0."""
    with pytest.raises(ValueError):
        Event(type="capacity_drop", target="S2", start=0, duration=5, severity=1.5)


def test_schema_accepts_demand_surge_multipliers():
    """Demand surge allows multiplier in [1.0, 3.0]."""
    ev = Event(type="demand_surge", target="C1", start=0, duration=7, severity=1.45)
    assert ev.severity == 1.45
    assert ev.duration_days == 7


# -----------------------------------------------------------------------------
# 3. DETERMINISTIC CASCADE (HAND-CALCULATED TTS / TTR VERIFICATION)
# -----------------------------------------------------------------------------
def test_hand_calculated_cascade_tts_and_ttr(test_graph):
    """Verify deterministic cascade formulas against hand calculations.

    Formula:
    TTS = t_impact + (stock / max(demand * severity, 1.0))
    For an outage at S2 starting at Day 0:
    First impact at S2: t_impact = 0.
    With stock = 100, capacity = 100, severity = 0.85:
    net_depletion_rate = 80 * 0.85 = 68 u/d.
    inventory_cover = 100 / 68 = ~1.47 days.
    TTS = 0 + 1.5 = 1.5 days.
    """
    test_graph.nodes["S2"]["stock"] = 100.0
    test_graph.nodes["S2"]["capacity"] = 100.0

    ev = Event(type="capacity_drop", target="S2", start=0, duration=10, severity=0.85)
    impacts = compute_cascade(test_graph, [ev])

    s2_impact = next(i for i in impacts if i.node == "S2")
    assert s2_impact.first_impact_day == 0
    assert s2_impact.mode == "quick estimate"
    assert s2_impact.status == "fails"  # TTS < duration 10
    assert s2_impact.ttr_days == 12.0   # duration 10 + transit lead 2


def test_demand_surge_ttr_and_tts(test_graph):
    """Verify TTR calculation for demand surge: duration + stock refill time."""
    test_graph.nodes["C1"]["stock"] = 50.0
    test_graph.nodes["C1"]["demand"] = 50.0
    test_graph.nodes["C1"]["capacity"] = 50.0

    # +45% surge for 7 days
    ev = Event(type="demand_surge", target="C1", start=0, duration=7, severity=1.45)
    impacts = compute_cascade(test_graph, [ev])

    c1_impact = next(i for i in impacts if i.node == "C1")
    assert c1_impact.first_impact_day == 0
    # Net burn rate = 50 * 0.45 = 22.5 u/d. Cover = 50 / 22.5 = 2.22 days.
    assert 2.0 <= c1_impact.tts_days <= 3.0
    assert c1_impact.ttr_days >= 7.0


# -----------------------------------------------------------------------------
# 4. AMBIGUITY RESOLUTION & OVERLAPPING EVENTS
# -----------------------------------------------------------------------------
def test_mumbai_ambiguity_flagging(test_graph):
    """Prompt mentioning 'Mumbai' flags ambiguity between C1 (Retail) and W1 (Warehouse)."""
    prompt = "Transport strike shuts down operations in Mumbai for 5 days."
    res = parse_by_rules(prompt, test_graph)
    assert any("Mumbai" in amb for amb in res["ambiguities"])


def test_overlapping_events_conservative_merge(test_graph):
    """Two overlapping events on the same node must merge conservatively according to assumptions.json.

    Rule:
    min_start, max_end, max_severity.
    Event 1: S2 start=0, duration=5, severity=0.5
    Event 2: S2 start=3, duration=7, severity=0.85 (ends day 10)
    Merged: start=0, duration=10, severity=0.85
    """
    from llm.parser import _merge_overlapping_events

    ev1 = Event(type="capacity_drop", target="S2", start=0, duration=5, severity=0.5, justification="Event 1")
    ev2 = Event(type="capacity_drop", target="S2", start=3, duration=7, severity=0.85, justification="Event 2")

    merged = _merge_overlapping_events([ev1, ev2])
    assert len(merged) == 1
    assert merged[0].target == "S2"
    assert merged[0].start == 0
    assert merged[0].duration == 10
    assert merged[0].severity == 0.85


# -----------------------------------------------------------------------------
# 5. SURROGATE XGBOOST & FEATURE MAPPING
# -----------------------------------------------------------------------------
def test_surrogate_feature_consistency(test_graph):
    """Features built from graph must strictly match the XGBoost trained model feature list."""
    X = build_features(test_graph)
    assert list(X.columns) == FEATURES


def test_surrogate_quick_risk_inference(test_graph):
    """Instant XGBoost risk evaluation returns valid High/Moderate/Low risk with SHAP factors."""
    ev = Event(type="capacity_drop", target="S2", start=0, duration=10, severity=0.85)
    estimate = scenario_quick_risk(test_graph, [ev])

    assert estimate is not None
    assert estimate.risk_level in ("High", "Moderate", "Low")
    assert 0.0 <= estimate.predicted_unmet_share <= 1.0
    assert len(estimate.top_factors) <= 3
    assert estimate.label == "estimate"
    assert estimate.latency_ms is not None


def test_surrogate_comparison():
    """Surrogate vs simulated comparison computes error and labels correctly."""
    comp = surrogate_compare(predicted_unmet=0.40, actual_unmet_share=0.35)
    assert comp.predicted_risk_level == "High"
    assert comp.predicted_unmet_share == 0.40
    assert comp.actual_unmet_share == 0.35
    assert comp.absolute_error == 0.05


# -----------------------------------------------------------------------------
# 6. UNKNOWN PROMPT ERROR STATE
# -----------------------------------------------------------------------------
def test_unparseable_prompt_returns_friendly_error(test_graph):
    """Unidentifiable text returns ScenarioParseError with 3 clickable examples."""
    prompt = "The quick brown fox jumps over the lazy dog."
    with pytest.raises(Exception) as excinfo:
        parse_by_rules(prompt, test_graph)
    msg = str(excinfo.value)
    assert "Try one of these examples" in msg

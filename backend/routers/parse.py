from fastapi import APIRouter, HTTPException

from config import settings
from core.cascade import compute_cascade
from core.followups import generate_data_followups
from core.risk_ml import scenario_quick_risk
from llm.parser import LLMUnavailable, ScenarioParseError, parse_scenario_full
from mock import mock_data
from routers.deps import check_events, get_graph, use_mock
from schemas import Event, ParseRequest, ParseResponse

router = APIRouter(tags=["parse"])


@router.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest):
    mock = use_mock(settings.mock_parse)
    G = get_graph()
    if mock:
        raw = mock_data.parse(req.text)
        validated_events = [Event.model_validate(e) for e in raw.get("events", [])]
        check_events(validated_events, mock=True)
        cascade = compute_cascade(G, validated_events)
        followups = generate_data_followups(G, validated_events)
        risk = scenario_quick_risk(G, validated_events)
        return ParseResponse(
            events=validated_events,
            interpreted_narrative=raw.get("interpreted_narrative", "Scenario parsed."),
            ambiguities=raw.get("ambiguities", []),
            confidence=raw.get("confidence", 0.9),
            source=raw.get("source", "rules"),
            suggested_followups=followups,
            cascade_preview=cascade,
            ml_quick_risk=risk,
        )

    if not mock and settings.llm_provider == "claude":
        try:
            from llm.parser import parse_scenario
            events = parse_scenario(req.text, G)
            check_events(events, mock=False)
            cascade = compute_cascade(G, events)
            followups = generate_data_followups(G, events)
            risk = scenario_quick_risk(G, events)
            return ParseResponse(
                events=events,
                interpreted_narrative="Parsed via Claude LLM.",
                confidence=0.95,
                source="llm",
                cascade_preview=cascade,
                suggested_followups=followups,
                ml_quick_risk=risk,
            )
        except LLMUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ScenarioParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return parse_scenario_full(req.text, G)
    except ScenarioParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parse failure: {exc}") from exc

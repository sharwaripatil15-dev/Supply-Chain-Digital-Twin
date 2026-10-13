from fastapi import APIRouter, HTTPException

from config import settings
from llm.parser import LLMUnavailable, ScenarioParseError, parse_scenario
from mock import mock_data
from routers.deps import check_events, get_graph, use_mock
from schemas import Event, ParseRequest, ParseResponse

router = APIRouter(tags=["parse"])


def _live_parse(text: str) -> dict:
    # Error details are written for the UI, which shows them above the event-builder dropdowns.
    try:
        return {"events": parse_scenario(text, get_graph())}
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScenarioParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest):
    mock = use_mock(settings.mock_parse)  # mock events name preset ids, so other networks use the real parser
    compute = mock_data.parse if mock else _live_parse
    result = compute(req.text)
    # never trust LLM output unvalidated
    check_events([Event.model_validate(e) for e in result["events"]], mock=mock)
    return result

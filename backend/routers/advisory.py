from fastapi import APIRouter

from cache import cache
from config import settings
from core.ai_advisory import analyze_network_and_recommend
from routers.deps import cache_scope, get_graph, use_mock
from schemas import AdvisoryResponse

router = APIRouter(tags=["advisory"])


@router.get("/ai-advisory", response_model=AdvisoryResponse)
def get_ai_advisory():
    """AI/ML-based network vulnerability analysis and prioritized strategic recommendations."""
    G = get_graph()
    mock = use_mock(settings.mock_network)
    return cache.get_or_compute(
        cache.key("ai_advisory", cache_scope(mock)),
        lambda: analyze_network_and_recommend(G),
    )

"""What-if recovery planner (core/whatif.py). Always the real engine, on the network the UI shows.

POST /whatif/run       plain English (`text`) or structured `events` -> evidence, narrative sections, plans, brief
POST /whatif/ask       follow-up question on a run, answered through a whitelist of engine tools
GET  /whatif/history   recent runs (summaries)
POST /whatif/compare   2-4 runs side by side
GET  /whatif/{id}      one full run;  GET /whatif/{id}/brief  the Markdown brief
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.concurrency import run_in_threadpool

from config import settings
from core import whatif as wi
from core.graph import node_index
from network_store import store
from routers.deps import display_graph, require_runnable
from schemas import WhatIfAskRequest, WhatIfCompareRequest, WhatIfRunRequest
from validation import EventValidationError, validate_events

router = APIRouter(prefix="/whatif", tags=["what-if"])


def _network() -> dict:
    return {"source": store.source, "version": store.version}


def _run(req: WhatIfRunRequest) -> dict:
    G = display_graph()
    notes: list[str] = []
    parser = "builder"
    if req.events:
        try:
            events = validate_events(req.events, *node_index(G))
        except EventValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        try:
            events, notes, parser = wi.parse_question(req.text or "", G, req.horizon)
        except wi.WhatIfError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = wi.run_whatif(G, events, horizon=req.horizon, mc_runs=req.mc_runs, robustness_runs=req.robustness_runs,
                           seed=req.seed, assumptions=notes, question=req.text, parser=parser)
    wi.history.add(result, _network())
    return result


@router.post("/run")
async def whatif_run(req: WhatIfRunRequest):
    require_runnable()
    return await run_in_threadpool(_run, req)


def _get(run_id: str) -> dict:
    run = wi.history.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown what-if run {run_id!r} (history keeps the last {wi.MAX_HISTORY}).")
    return run


@router.post("/ask")
async def whatif_ask(req: WhatIfAskRequest):
    run = _get(req.run_id)
    if run.get("status") != "ok":
        raise HTTPException(status_code=409, detail="That run has no scenario to ask about.")
    if run.get("network") != _network():
        raise HTTPException(status_code=409, detail="The network changed since this run; run the what-if again first.")
    router_fn = None
    if settings.anthropic_api_key:
        from llm.parser import route_question

        router_fn = route_question
    return await run_in_threadpool(wi.ask, display_graph(), run, req.question, router_fn)


@router.get("/history")
def whatif_history():
    current = _network()
    return {"runs": [{**r, "stale": r["network"] != current} for r in wi.history.list()], "limit": wi.MAX_HISTORY}


@router.post("/compare")
def whatif_compare(req: WhatIfCompareRequest):
    try:
        return wi.compare(req.ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc


@router.get("/{run_id}")
def whatif_get(run_id: str):
    return _get(run_id)


@router.get("/{run_id}/brief", response_class=Response, responses={200: {"content": {"text/markdown": {}}}})
def whatif_brief(run_id: str):
    run = _get(run_id)
    return Response(content=run["brief_markdown"], media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="whatif-{run_id}.md"'})

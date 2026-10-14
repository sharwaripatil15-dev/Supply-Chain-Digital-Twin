"""Expansion planner (core/expansion.py). Always the real engine, on the network the UI shows.

GET  /expansion/candidates            the candidate library + custom / auto sites, with exclusions
POST /expansion/candidates            {action: add | remove | exclude | include | auto | reset, ...}
GET  /expansion/baseline              today's KPIs from the flow engine (service level, lead time, stock cover, ...)
POST /expansion/run                   start a run (?wait=true blocks); returns {id, status, progress}
GET  /expansion/results/{id}          progress, or the result (plans, cross-check, marginal values, sensitivity)
POST /expansion/results/{id}/cancel   cancel a running job
GET  /expansion/latest                the latest finished result for the current network version (or {status: none})
POST /expansion/apply {plan_id}       add the plan's sites and lanes through the Manual Builder (one import, so the UI can
                                      undo it in one step); bumps the network version and clears caches
"""
from __future__ import annotations

import threading
import time
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import builder
from core import expansion as ex
from network_store import store
from routers.deps import display_graph, require_runnable
from schemas import MAX_EDGES, MAX_NODES

router = APIRouter(prefix="/expansion", tags=["expansion"])
KEEP = 10


class RunRequest(BaseModel):
    goal: str = "balanced"
    types: list[str] = Field(default_factory=lambda: ["warehouse", "factory"])
    n_add: int = Field(default=1, ge=1, le=5)
    budget: float | None = Field(default=None, ge=0, description="INR, on build cost")
    max_lead_days: float = Field(default=ex.DEFAULT_MAX_LEAD, gt=0, le=60)
    weather: bool = False
    co2: bool = False
    growth: float = Field(default=ex.DEFAULT_GROWTH, ge=-0.5, le=2.0, description="planning demand growth")
    redundancy: bool = False
    max_per_type: dict[str, int] = Field(default_factory=dict)
    candidate_ids: list[str] | None = None


class CandidateAction(BaseModel):
    action: str = Field(description="add | remove | exclude | include | auto | reset")
    id: str | None = None
    name: str | None = Field(default=None, max_length=60)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    fixed_cost: float | None = Field(default=None, ge=0, description="build cost, INR")
    capacity: float | None = Field(default=None, gt=0, description="units/day")
    types: list[str] | None = None
    n: int = Field(default=4, ge=1, le=10)


class ApplyRequest(BaseModel):
    plan_id: str


class Jobs:
    def __init__(self):
        self._lock = threading.Lock()
        self.jobs: dict[str, dict] = {}

    def start(self, params: dict) -> dict:
        G = display_graph()
        jid = uuid.uuid4().hex[:8]
        job = {"id": jid, "status": "running", "progress": {"step": "Starting", "done": 0, "total": 8}, "started": time.time(),
               "network": {"source": store.source, "version": store.version}, "cancel": threading.Event(), "result": None,
               "error": None, "thread": None}

        def progress(step, done, total):
            job["progress"] = {"step": step, "done": done, "total": total}

        def work():
            try:
                res = ex.run_expansion(G, params, progress=progress, cancelled=job["cancel"].is_set)
                res.update(job_id=jid, network=job["network"], generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                job["result"] = res
                job["status"] = "done"
            except ex.Cancelled:
                job["status"] = "cancelled"
            except ex.ExpansionError as exc:
                job["status"], job["error"] = "error", str(exc)
            except Exception as exc:  # noqa: BLE001
                job["status"], job["error"] = "error", f"{type(exc).__name__}: {str(exc)[:200]}"

        with self._lock:
            self.jobs[jid] = job
            for old in list(self.jobs)[:-KEEP]:
                self.jobs.pop(old)
        job["thread"] = threading.Thread(target=work, daemon=True, name="aegis-expansion")
        job["thread"].start()
        return job

    def get(self, jid: str) -> dict | None:
        return self.jobs.get(jid)

    def plan(self, plan_id: str) -> tuple[dict, dict] | None:
        for job in self.jobs.values():
            for p in ((job.get("result") or {}).get("plans") or []):
                if p["id"] == plan_id:
                    return job, p
        return None

    def latest(self) -> dict | None:
        cur = {"source": store.source, "version": store.version}
        done = [j for j in self.jobs.values() if j["status"] == "done" and j["network"] == cur]
        return done[-1] if done else None

    def clear(self):
        with self._lock:
            self.jobs.clear()


jobs = Jobs()


def public(job: dict | None) -> dict:
    if job is None:
        return {"status": "none"}
    if job["status"] == "done":
        return job["result"]
    base = {"id": job["id"], "status": job["status"], "network": job["network"]}
    if job["status"] == "running":
        return {**base, "progress": job["progress"], "elapsed_s": round(time.time() - job["started"], 1)}
    return {**base, "detail": job["error"] or "Cancelled."}


@router.get("/candidates")
def get_candidates():
    return {"note": ex.candidates.note, "sites": ex.candidates.all(), "types": list(ex.TYPES)}


@router.post("/candidates")
def edit_candidates(req: CandidateAction):
    c = ex.candidates
    try:
        if req.action == "add":
            if req.name is None or req.lat is None or req.lon is None:
                raise HTTPException(422, "A custom candidate needs a name, lat and lon.")
            c.add({"name": req.name, "lat": req.lat, "lon": req.lon, "fixed_cost": req.fixed_cost, "capacity": req.capacity,
                   "types": [t for t in (req.types or []) if t in ex.TYPES] or None})
        elif req.action in ("exclude", "include"):
            c.exclude(req.id or "", req.action == "exclude")
        elif req.action == "remove":
            c.remove(req.id or "")
        elif req.action == "auto":
            require_runnable()
            ex.auto_candidates(display_graph(), req.n)
        elif req.action == "reset":
            c.reset()
        else:
            raise HTTPException(422, f"Unknown action {req.action!r}.")
    except ex.ExpansionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return get_candidates()


@router.get("/baseline")
def baseline():
    return ex.baseline_kpis(display_graph()) if not store.active_errors() else {"status": "empty"}


@router.post("/run")
async def run(req: RunRequest, wait: bool = Query(False)):
    require_runnable()
    try:
        params = ex.normalize(req.model_dump())
    except ex.ExpansionError as exc:
        raise HTTPException(422, str(exc)) from exc
    job = jobs.start(params)
    if wait:
        await run_in_threadpool(job["thread"].join)
    return public(job)


@router.get("/results/{job_id}")
def results(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown expansion run {job_id!r}.")
    return public(job)


@router.post("/results/{job_id}/cancel")
def cancel(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown expansion run {job_id!r}.")
    job["cancel"].set()
    if job["thread"] is not None:
        job["thread"].join(timeout=30)
    return public(job)


@router.get("/latest")
def latest():
    return public(jobs.latest())


def _records() -> tuple[list[dict], list[dict]]:
    """The active network as builder records (the manual records themselves when the manual network is active)."""
    if store.source == "manual":
        return [dict(n) for n in store.manual_nodes()], [dict(e) for e in store.manual_edges()]
    return builder.graph_to_builder(display_graph())


@router.post("/apply")
def apply(req: ApplyRequest):
    found = jobs.plan(req.plan_id)
    if not found:
        raise HTTPException(404, f"Unknown plan {req.plan_id!r}.")
    job, plan = found
    if job["network"] != {"source": store.source, "version": store.version}:
        raise HTTPException(409, "The network changed since this plan was computed; run the expansion planner again.")
    nodes, edges = _records()
    adds = plan["additions"]
    if len(nodes) + len(adds["nodes"]) > MAX_NODES or len(edges) + len(adds["edges"]) > MAX_EDGES:
        raise HTTPException(422, f"Adding this plan would exceed the manual network limit of {MAX_NODES} nodes / {MAX_EDGES} lanes.")
    taken = {n["id"] for n in nodes}
    rename = {}
    for n in adds["nodes"]:
        nid = n["id"]
        while nid in taken:
            nid = builder.node_id_for(n["kind"], taken)
        rename[n["id"]] = nid
        taken.add(nid)
        rec = {"id": nid, "name": n["name"][:80], "kind": n["kind"], "city": n["city"], "lat": n["lat"], "lon": n["lon"],
               "capacity": float(n["capacity"]), "stock": float(n["stock"]), "reliability": 0.95, "op_cost": 0.0, "status": "active"}
        nodes.append(rec)
    eids = {e["id"] for e in edges}
    added_edges = []
    for e in adds["edges"]:
        eid = builder.next_id("E", eids)
        eids.add(eid)
        rec = {"id": eid, "source": rename.get(e["source"], e["source"]), "target": rename.get(e["target"], e["target"]),
               "mode": e.get("mode") or "road", "distance_km": e.get("distance_km"), "lead": e["lead"], "capacity": e["capacity"],
               "cost": e["cost"], "co2": e["co2"], "status": "active"}
        edges.append(rec)
        added_edges.append(rec)
    previous = {"source": store.source, "version": store.version}
    store.replace_manual(nodes, edges, activate=True)
    return {"applied": req.plan_id, "previous": previous, "source": store.source, "version": store.version,
            "added_nodes": [rename[n["id"]] for n in adds["nodes"]], "added_edges": [e["id"] for e in added_edges]}

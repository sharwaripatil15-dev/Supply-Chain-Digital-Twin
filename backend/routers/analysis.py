"""Bottleneck and pain-point analyzer (core/bottleneck.py). Always the real engine, on the network the UI shows.

POST /analysis/run              start (or return the cached) analysis of the active network; ?wait=true blocks until done,
                                ?force=true re-runs even if this network version was already analysed
GET  /analysis/latest           the result for the current network version, or {status: running, progress} / {status: none}
GET  /analysis/finding/{id}     one finding of the latest result
Results are cached per (source, network version), so any edit to the network invalidates them.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from core import bottleneck
from core.hazards import service as weather_service
from network_store import store
from routers.deps import display_graph, require_runnable

router = APIRouter(prefix="/analysis", tags=["analysis"])
log = logging.getLogger("aegis.analysis")
WEATHER_TIMEOUT_S = 8.0


class Jobs:
    def __init__(self):
        self._lock = threading.Lock()
        self.jobs: dict[tuple, dict] = {}

    def get(self, key: tuple) -> dict | None:
        return self.jobs.get(key)

    def start(self, key: tuple, weather: dict | None, quality: str | None) -> dict:
        with self._lock:
            job = self.jobs.get(key)
            if job and job["status"] == "running":
                return job
            for k in [k for k in self.jobs if k != key]:  # results for older network versions are stale
                self.jobs.pop(k)
            job = {"status": "running", "progress": {"step": "Starting", "done": 0, "total": 10}, "started": time.time(),
                   "thread": None, "result": None, "error": None}
            self.jobs[key] = job
        G = display_graph()

        def progress(step: str, done: int, total: int) -> None:
            job["progress"] = {"step": step, "done": done, "total": total}

        def work():
            try:
                res = bottleneck.analyze(G, weather=weather, progress=progress)
                res.update(network={"source": key[0], "version": key[1]}, weather_data_quality=quality,
                           generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                job["result"] = res
                job["status"] = "done"
            except Exception as exc:  # noqa: BLE001 - reported to the client instead of a stack trace
                log.exception("analysis failed")
                job["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                job["status"] = "error"

        t = threading.Thread(target=work, daemon=True, name="aegis-analysis")
        job["thread"] = t
        t.start()
        return job

    def clear(self) -> None:
        with self._lock:
            self.jobs.clear()


jobs = Jobs()


def _key() -> tuple:
    return (store.source, store.version)


def _public(job: dict | None) -> dict:
    if job is None:
        return {"status": "none", "network": {"source": store.source, "version": store.version}}
    if job["status"] == "done":
        return job["result"]
    if job["status"] == "error":
        return {"status": "error", "detail": job["error"]}
    return {"status": "running", "progress": job["progress"], "elapsed_s": round(time.time() - job["started"], 1)}


async def _weather(G) -> tuple[dict | None, str | None]:
    """Peak forecast risk per lane from the hazard service (cached / simulated / calm); never fails the analysis."""
    try:
        risk = await asyncio.wait_for(weather_service.assess(G, 7), WEATHER_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        log.info("analysis without weather data: %s", exc)
        return None, None
    out = {}
    for e in risk.get("edges", []):
        daily = e.get("daily") or []
        if daily:
            worst = max(daily, key=lambda d: d.get("risk", 0))
            out[e["id"]] = {"peak_risk": round(float(worst.get("risk", 0)), 3), "level": worst.get("level"),
                            "reason": (worst.get("reason") or "")[:160]}
    return out, risk.get("data_quality")


@router.post("/run")
async def analysis_run(wait: bool = Query(False), force: bool = Query(False)):
    require_runnable()
    key = _key()
    job = jobs.get(key)
    if job and job["status"] == "done" and not force:
        return job["result"]
    if not job or job["status"] != "running" or force:
        weather, quality = await _weather(display_graph())
        job = jobs.start(key, weather, quality)
    if wait:
        await run_in_threadpool(job["thread"].join)
    return _public(job)


@router.get("/latest")
def analysis_latest():
    return _public(jobs.get(_key()))


@router.get("/finding/{finding_id}")
def analysis_finding(finding_id: str):
    job = jobs.get(_key())
    if not job or job["status"] != "done":
        raise HTTPException(status_code=404, detail="No analysis for the current network yet: run POST /analysis/run.")
    for f in job["result"]["findings"]:
        if f["id"] == finding_id:
            return f
    raise HTTPException(status_code=404, detail=f"Unknown finding {finding_id!r}.")

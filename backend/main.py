"""AEGIS API - AI Supply Chain Digital Twin & Disruption Simulator."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from network_store import NetworkEditError, store
from routers import chaos, forecast, network, network_builder, parse, recover, simulate, upload, weather

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aegis")

app = FastAPI(
    title="AEGIS API",
    version="0.2.0",
    description="Supply-chain digital twin: simulate disruptions, find hidden failure points, plan safe recoveries.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (network_builder, network, simulate, chaos, recover, parse, forecast, upload, weather):
    app.include_router(r.router)


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(_: Request, exc: NotImplementedError):
    return JSONResponse(
        status_code=501,
        content={"detail": f"Not implemented yet: {exc}. Set the matching USE_MOCK_* flag to true to use mock data."},
    )


@app.exception_handler(NetworkEditError)
async def network_edit_handler(_: Request, exc: NetworkEditError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    """Last resort: a JSON body with a short reason, never a stack trace (that goes to the server log)."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error while handling {request.url.path}: {type(exc).__name__}: {str(exc)[:200]}"},
    )


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "mock": settings.mock_flags(), "network": {"source": store.source, "version": store.version}}

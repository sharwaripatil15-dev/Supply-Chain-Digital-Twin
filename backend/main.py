"""AEGIS API - AI Supply Chain Digital Twin & Disruption Simulator."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from routers import chaos, forecast, network, parse, recover, simulate, upload

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="AEGIS API",
    version="0.1.0",
    description="Supply-chain digital twin: simulate disruptions, find hidden failure points, plan safe recoveries.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (network, simulate, chaos, recover, parse, forecast, upload):
    app.include_router(r.router)


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(_: Request, exc: NotImplementedError):
    return JSONResponse(
        status_code=501,
        content={"detail": f"Not implemented yet: {exc}. Set the matching USE_MOCK_* flag to true to use mock data."},
    )


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "mock": settings.mock_flags()}

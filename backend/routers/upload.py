"""POST /upload: load a network from nodes.csv + edges.csv (parsing and validation are real, not mocked)."""
import io

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from config import settings
from core.graph import GraphDataError, graph_from_tables, graph_to_payload
from routers.deps import set_graph
from schemas import UploadResponse

router = APIRouter(tags=["upload"])


async def _read_csv(f: UploadFile, label: str) -> pd.DataFrame:
    raw = await f.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, f"{label} is larger than {settings.max_upload_bytes // 1_000_000} MB")
    try:
        return pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
    except Exception as exc:
        raise HTTPException(422, f"{label} is not a readable CSV: {exc}") from exc


@router.post("/upload", response_model=UploadResponse)
async def upload(
    nodes: UploadFile = File(..., description="nodes.csv: id,kind,city,lat,lon,capacity,stock,demand[,name,reliability,utilization,backup,risk]"),
    edges: UploadFile = File(..., description="edges.csv: source,target,capacity,lead,cost[,co2]"),
    activate: bool = Query(False, description="use this network for core/ (non-mock) routers until restart"),
):
    try:
        G, warnings = graph_from_tables(await _read_csv(nodes, "nodes.csv"), await _read_csv(edges, "edges.csv"))
    except GraphDataError as exc:
        raise HTTPException(422, str(exc)) from exc
    if activate:
        set_graph(G)
    kinds = [d["kind"] for _, d in G.nodes(data=True)]
    return {
        "network": graph_to_payload(G, resilience_score=None),
        "summary": {"n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
                    "by_kind": {k: kinds.count(k) for k in sorted(set(kinds))}},
        "warnings": warnings,
        "activated": activate,
    }

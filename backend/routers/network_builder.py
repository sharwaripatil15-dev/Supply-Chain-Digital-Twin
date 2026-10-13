"""Manual network builder and active-source switching (preset | csv | manual). Owner: D.

Every mutation goes through network_store.store, which bumps the network version, rebuilds the engine graph,
clears graph-dependent caches and persists to data/active_network.json. Mutation responses carry the new version
and the manual network's validation report so the UI never needs a second round trip.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Query, Response

import builder
from network_store import store
from routers.deps import get_graph, preset_graph
from schemas import (
    BuilderEdge,
    BuilderNetwork,
    BuilderNode,
    EdgeMutationResponse,
    ExportedNetwork,
    ManualNetworkResponse,
    NetworkSourceInfo,
    NodeMutationResponse,
    SetSourceRequest,
    ValidationReport,
)

router = APIRouter(prefix="/network", tags=["network builder"])


def _manual() -> dict:
    return {"source": store.source, "version": store.version, "nodes": store.manual_nodes(),
            "edges": store.manual_edges(), "validation": store.report()}


# ---------------------------------------------------------------- source
@router.get("/source", response_model=NetworkSourceInfo)
def get_source():
    return store.info()


@router.put("/source", response_model=NetworkSourceInfo)
def set_source(req: SetSourceRequest):
    """Activate a source. `manual` is refused (409) while the manual network has validation errors."""
    store.set_source(req.source)
    return store.info()


@router.get("/manual", response_model=ManualNetworkResponse)
def get_manual():
    """The manual network as the builder edits it (whether or not it is the active source)."""
    return _manual()


# ---------------------------------------------------------------- nodes
@router.post("/nodes", response_model=NodeMutationResponse, status_code=201)
def create_node(node: BuilderNode):
    created = store.add_node(node.model_dump())
    return {"node": created, "removed_edges": [], "version": store.version, "validation": store.report()}


@router.put("/nodes/{node_id}", response_model=NodeMutationResponse)
def update_node(node_id: str, node: BuilderNode):
    updated = store.update_node(node_id, node.model_dump())
    return {"node": updated, "removed_edges": [], "version": store.version, "validation": store.report()}


@router.delete("/nodes/{node_id}", response_model=NodeMutationResponse)
def delete_node(node_id: str):
    """Deletes the node and every lane touching it; the removed lanes are returned."""
    node, removed = store.delete_node(node_id)
    return {"node": node, "removed_edges": removed, "version": store.version, "validation": store.report()}


# ---------------------------------------------------------------- edges
@router.post("/edges", response_model=EdgeMutationResponse, status_code=201)
def create_edge(edge: BuilderEdge):
    created = store.add_edge(edge.model_dump())
    return {"edge": created, "version": store.version, "validation": store.report()}


@router.put("/edges/{edge_id}", response_model=EdgeMutationResponse)
def update_edge(edge_id: str, edge: BuilderEdge):
    updated = store.update_edge(edge_id, edge.model_dump())
    return {"edge": updated, "version": store.version, "validation": store.report()}


@router.delete("/edges/{edge_id}", response_model=EdgeMutationResponse)
def delete_edge(edge_id: str):
    removed = store.delete_edge(edge_id)
    return {"edge": removed, "version": store.version, "validation": store.report()}


# ---------------------------------------------------------------- whole network
@router.post("/validate", response_model=ValidationReport)
def validate(network: BuilderNetwork | None = Body(default=None)):
    """Validate a draft network (body) or, with no body, the stored manual network."""
    if network is None:
        return store.report()
    return builder.validate([n.model_dump() for n in network.nodes], [e.model_dump() for e in network.edges])


@router.post("/reset", response_model=ManualNetworkResponse)
def reset(to: Literal["preset", "empty"] = Query(..., description="preset: copy the preset into the builder and make "
                                                                   "the preset active; empty: clear the manual network")):
    store.reset(to, preset_graph() if to == "preset" else None)
    return _manual()


@router.get("/export", response_model=ExportedNetwork)
def export(scope: Literal["manual", "active", "preset"] = "manual"):
    """Builder JSON (re-importable with POST /network/import). active/preset convert an engine graph."""
    if scope == "manual":
        nodes, edges = store.manual_nodes(), store.manual_edges()
    else:
        nodes, edges = builder.graph_to_builder(preset_graph() if scope == "preset" or store.source == "preset" else get_graph())
    return {"source": store.source if scope != "preset" else "preset", "version": store.version, "nodes": nodes, "edges": edges}


@router.get("/export/csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_csv(file: Literal["nodes", "edges"] = "nodes", scope: Literal["manual", "active"] = "manual"):
    """nodes.csv or edges.csv in the format POST /upload accepts (active nodes and lanes only)."""
    if scope == "manual":
        G = builder.build_graph(dict((n["id"], n) for n in store.manual_nodes()), dict((e["id"], e) for e in store.manual_edges()))
    else:
        G = preset_graph() if store.source == "preset" else get_graph()
    nodes_csv, edges_csv = builder.to_csv(G)
    return Response(
        content=nodes_csv if file == "nodes" else edges_csv,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file}.csv"'},
    )


@router.post("/import", response_model=ManualNetworkResponse)
def import_network(network: BuilderNetwork, activate: bool = Query(False, description="also make it the active network")):
    """Replace the manual network (e.g. a file from GET /network/export). Structural problems -> 422, nothing changes."""
    store.replace_manual([n.model_dump() for n in network.nodes], [e.model_dump() for e in network.edges], activate=activate)
    return _manual()

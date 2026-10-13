"""The active network: the single source of truth behind every router. Owner: D.

Three sources produce the same thing, an engine graph (networkx.DiGraph) that /network, /simulate, /chaos, /recover,
/forecast and /parse all use:
    preset  the demo network (the mock payloads while USE_MOCK_* is on, core.graph.build_network otherwise)
    csv     the last CSV upload activated with POST /upload?activate=true
    manual  the network edited in the builder (routers/network_builder.py)
Every change (an edit to the manual network, a CSV activation, a source switch) runs under one lock, bumps `version`,
rebuilds the graph from the stored records, clears every graph-dependent cache and persists the state to
DATA_DIR/active_network.json with an atomic write. A missing file means a fresh start on the preset; an unreadable
one is set aside as active_network.corrupt.json and the app also starts on the preset (see `note`).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

import networkx as nx
from pydantic import ValidationError

import builder
from config import settings
from node_types import edge_allowed
from schemas import MAX_EDGES, MAX_NODES, BuilderNetwork

log = logging.getLogger("aegis.network")

FILE_NAME = "active_network.json"
FILE_FORMAT = "aegis-active-network"
SOURCES = ("preset", "csv", "manual")


class NetworkEditError(Exception):
    """A rejected edit. `detail` is a string or a FastAPI-style [{loc, msg, type}] list (rendered as HTTP `status`)."""

    def __init__(self, status: int, detail):
        super().__init__(detail if isinstance(detail, str) else "; ".join(d["msg"] for d in detail))
        self.status = status
        self.detail = detail


def _field_error(field: str, msg: str) -> list[dict]:
    return [{"loc": ["body", field], "msg": msg, "type": "value_error"}]


class NetworkStore:
    def __init__(self, path: Path):
        self._lock = threading.RLock()
        self.path = Path(path)
        self.source = "preset"
        self.version = 1
        self.nodes: dict[str, dict] = {}  # manual network, insertion-ordered
        self.edges: dict[str, dict] = {}
        self.csv_graph: nx.DiGraph | None = None
        self.note: str | None = None
        self._manual_graph = nx.DiGraph()
        self._report = builder.validate([], [])
        self._load()

    # ------------------------------------------------------------ reads
    def graph(self) -> nx.DiGraph | None:
        """Engine graph of the active source; None means the preset (routers.deps supplies it)."""
        if self.source == "manual":
            return self._manual_graph
        if self.source == "csv":
            return self.csv_graph
        return None

    def report(self) -> dict:
        """Validation report of the manual network."""
        return self._report

    def active_errors(self) -> list[dict]:
        if self.source == "manual":
            return self._report["errors"]
        if self.source == "csv":
            return builder.graph_errors(self.csv_graph)
        return []

    def manual_nodes(self) -> list[dict]:
        return list(self.nodes.values())

    def manual_edges(self) -> list[dict]:
        return list(self.edges.values())

    def info(self) -> dict:
        G = self.graph()
        return {
            "source": self.source,
            "version": self.version,
            "node_count": G.number_of_nodes() if G is not None else -1,  # -1: preset (size reported by /network)
            "edge_count": G.number_of_edges() if G is not None else -1,
            "runnable": not self.active_errors(),
            "manual_node_count": len(self.nodes),
            "manual_edge_count": len(self.edges),
            "csv_loaded": self.csv_graph is not None,
            "note": self.note,
        }

    # ------------------------------------------------------------ manual edits
    def add_node(self, data: dict) -> dict:
        with self._lock:
            if len(self.nodes) >= MAX_NODES:
                raise NetworkEditError(422, _field_error("kind", f"Manual networks are limited to {MAX_NODES} nodes."))
            nid = data.get("id") or builder.node_id_for(data["kind"], self.nodes)
            if nid in self.nodes:
                raise NetworkEditError(422, _field_error("id", f"Node id {nid} already exists."))
            node = {**data, "id": nid}
            self.nodes[nid] = node
            self._commit()
            return node

    def update_node(self, nid: str, data: dict) -> dict:
        with self._lock:
            self._require_node(nid)
            if data.get("id") not in (None, nid):
                raise NetworkEditError(422, _field_error("id", "A node id can only be set when the node is created."))
            node = {**data, "id": nid}
            self.nodes[nid] = node  # lanes keep their stored distance/lead (they may be user overrides)
            self._commit()
            return node

    def delete_node(self, nid: str) -> tuple[dict, list[dict]]:
        with self._lock:
            node = self._require_node(nid)
            removed = [e for e in self.edges.values() if nid in (e["source"], e["target"])]
            for e in removed:
                del self.edges[e["id"]]
            del self.nodes[nid]
            self._commit()
            return node, removed

    def add_edge(self, data: dict) -> dict:
        with self._lock:
            if len(self.edges) >= MAX_EDGES:
                raise NetworkEditError(422, _field_error("source", f"Manual networks are limited to {MAX_EDGES} lanes."))
            eid = data.get("id") or builder.next_id("E", self.edges)
            if eid in self.edges:
                raise NetworkEditError(422, _field_error("id", f"Lane id {eid} already exists."))
            edge = self._checked_edge({**data, "id": eid})
            self.edges[eid] = edge
            self._commit()
            return edge

    def update_edge(self, eid: str, data: dict) -> dict:
        with self._lock:
            if eid not in self.edges:
                raise NetworkEditError(404, f"Lane {eid} not found.")
            if data.get("id") not in (None, eid):
                raise NetworkEditError(422, _field_error("id", "A lane id can only be set when the lane is created."))
            edge = self._checked_edge({**data, "id": eid})
            self.edges[eid] = edge
            self._commit()
            return edge

    def delete_edge(self, eid: str) -> dict:
        with self._lock:
            if eid not in self.edges:
                raise NetworkEditError(404, f"Lane {eid} not found.")
            edge = self.edges.pop(eid)
            self._commit()
            return edge

    def replace_manual(self, nodes: list[dict], edges: list[dict], activate: bool = False) -> None:
        """Import: swap the whole manual network after structural checks (duplicate ids, unknown endpoints ...)."""
        with self._lock:
            taken: set[str] = set()
            fixed_nodes = []
            for n in nodes:
                nid = n.get("id") or builder.node_id_for(n["kind"], taken | {x.get("id") for x in nodes if x.get("id")})
                taken.add(nid)
                fixed_nodes.append({**n, "id": nid})
            fixed_edges = []
            for e in edges:
                eid = e.get("id") or builder.next_id("E", {x["id"] for x in fixed_edges} | {x.get("id") for x in edges if x.get("id")})
                fixed_edges.append({**e, "id": eid})
            problems = builder.integrity_errors(fixed_nodes, fixed_edges)
            if problems:
                raise NetworkEditError(422, [{"loc": ["body", *p["refs"][:1]], "msg": p["message"], "type": p["code"]} for p in problems])
            by_id = {n["id"]: n for n in fixed_nodes}
            new_edges = {e["id"]: builder.resolve_edge(e, by_id) for e in fixed_edges}
            if activate:  # check before touching state, so a rejected import changes nothing
                errors = builder.validate(list(by_id.values()), list(new_edges.values()))["errors"]
                if errors:
                    raise NetworkEditError(409, self._blocked_message("imported", errors))
                self.source = "manual"
            self.nodes, self.edges = by_id, new_edges
            self._commit()

    def reset(self, to: str, preset_graph: nx.DiGraph | None = None) -> None:
        """to="empty": clear the manual network. to="preset": manual network := a copy of the preset, active = preset."""
        with self._lock:
            if to == "empty":
                self.nodes, self.edges = {}, {}
            elif to == "preset":
                nodes, edges = builder.graph_to_builder(preset_graph) if preset_graph is not None else ([], [])
                self.nodes = {n["id"]: n for n in nodes}
                self.edges = {e["id"]: e for e in edges}
                self.source = "preset"
            else:
                raise NetworkEditError(422, _field_error("to", "to must be 'preset' or 'empty'."))
            self._commit()

    # ------------------------------------------------------------ source switching
    def set_source(self, source: str) -> None:
        with self._lock:
            if source not in SOURCES:
                raise NetworkEditError(422, _field_error("source", f"source must be one of {', '.join(SOURCES)}."))
            if source == "csv" and self.csv_graph is None:
                raise NetworkEditError(409, "No CSV network has been uploaded yet. Upload one with 'Use as active network' checked.")
            if source == "manual" and self._report["errors"]:
                raise NetworkEditError(409, self._blocked_message("manual", self._report["errors"]))
            self.source = source
            self.note = None
            self._commit()

    def activate_csv(self, G: nx.DiGraph) -> None:
        with self._lock:
            G.graph.setdefault("unit_price", builder.UNIT_PRICE_INR)
            G.graph.setdefault("seed", settings.default_seed)
            self.csv_graph = G
            self.source = "csv"
            self._commit()

    def use_preset(self) -> None:
        """Back to the preset; also forgets any activated CSV (the old `set_graph(None)` behaviour)."""
        with self._lock:
            self.csv_graph = None
            self.source = "preset"
            self._commit()

    # ------------------------------------------------------------ internals
    def _require_node(self, nid: str) -> dict:
        if nid not in self.nodes:
            raise NetworkEditError(404, f"Node {nid} not found.")
        return self.nodes[nid]

    def _checked_edge(self, edge: dict) -> dict:
        src, dst = self.nodes.get(edge["source"]), self.nodes.get(edge["target"])
        if src is None:
            raise NetworkEditError(422, _field_error("source", f"Unknown node {edge['source']}."))
        if dst is None:
            raise NetworkEditError(422, _field_error("target", f"Unknown node {edge['target']}."))
        if not edge_allowed(src["kind"], dst["kind"]):
            raise NetworkEditError(422, _field_error("target", f"A {src['kind']} cannot ship to a {dst['kind']}."))
        clash = next((e["id"] for e in self.edges.values()
                      if e["id"] != edge["id"] and (e["source"], e["target"]) == (edge["source"], edge["target"])), None)
        if clash:
            raise NetworkEditError(422, _field_error("target", f"Lane {clash} already connects {edge['source']} -> {edge['target']}."))
        return builder.resolve_edge(edge, self.nodes)

    @staticmethod
    def _blocked_message(source: str, errors: list[dict]) -> str:
        return f"The {source} network can't run yet: " + " ".join(e["message"] for e in errors)

    def _rebuild(self) -> None:
        self._manual_graph = builder.build_graph(self.nodes, self.edges, seed=settings.default_seed)
        self._report = builder.validate(self.manual_nodes(), self.manual_edges())

    def _commit(self) -> None:
        """After every change: version++, rebuild from the records, drop graph-dependent caches, persist."""
        self.version += 1
        self._rebuild()
        invalidate_caches()
        self._save()

    def _save(self) -> None:
        state = {
            "format": FILE_FORMAT, "schema_version": 1, "source": self.source, "version": self.version,
            "manual": {"nodes": self.manual_nodes(), "edges": self.manual_edges()},
            "csv": builder.graph_to_dict(self.csv_graph) if self.csv_graph is not None else None,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:  # persistence is best-effort; the in-memory network still works
            log.warning("could not save %s: %s", self.path, exc)
            self.note = f"Changes are not being saved to disk ({exc.strerror or exc})."

    def _load(self) -> None:
        if not self.path.exists():
            self._rebuild()
            return
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if state.get("format") != FILE_FORMAT:
                raise ValueError("not an AEGIS network file")
            manual = BuilderNetwork.model_validate(state.get("manual") or {})
            nodes = [n.model_dump() for n in manual.nodes]
            edges = [e.model_dump() for e in manual.edges]
            if builder.integrity_errors(nodes, edges) or any(not x.get("id") for x in nodes + edges):
                raise ValueError("inconsistent node/lane ids")
            csv_graph = builder.graph_from_dict(state["csv"]) if state.get("csv") else None
            source = state.get("source") if state.get("source") in SOURCES else "preset"
            if source == "csv" and csv_graph is None:
                source = "preset"
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            log.warning("could not read %s (%s); starting from the preset", self.path, exc)
            self.note = f"The saved network could not be read ({type(exc).__name__}); started from the preset demo."
            try:
                os.replace(self.path, self.path.with_name("active_network.corrupt.json"))
            except OSError:
                pass
            self._rebuild()
            return
        self.nodes = {n["id"]: n for n in nodes}
        self.edges = {e["id"]: e for e in edges}
        self.csv_graph = csv_graph
        self.source = source
        self.version = max(1, int(state.get("version") or 1))
        self._rebuild()


def invalidate_caches() -> None:
    """Drop everything computed from a graph: API responses (memory + Redis), chaos scans, Monte Carlo, forecasts."""
    from cache import cache
    from core import chaos, forecast, montecarlo

    cache.clear()
    chaos._SCAN_CACHE.clear()
    montecarlo._CACHE.clear()
    forecast._CACHE.clear()


store = NetworkStore(Path(settings.data_dir) / FILE_NAME)

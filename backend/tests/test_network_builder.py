"""Manual network builder, active-source switching, persistence, and retailers running through every engine endpoint."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cache import cache
from core import chaos as chaos_core
from main import app
from network_store import NetworkStore, store
from schemas import (
    ChaosResponse,
    ForecastResponse,
    MonteCarloResponse,
    NetworkResponse,
    RecoverResponse,
    SimulateResponse,
    ValidationReport,
)

client = TestClient(app)
MOCK_DIR = Path(__file__).resolve().parent.parent / "mock"

SUPPLIER = dict(name="Pune Steel", kind="supplier", city="Pune", lat=18.52, lon=73.86, capacity=400, stock=500)
BACKUP = dict(name="Kolkata Backup", kind="supplier", city="Kolkata", lat=22.57, lon=88.36, capacity=200, stock=100, is_backup=True)
FACTORY = dict(name="Bengaluru Assembly", kind="factory", city="Bengaluru", lat=12.97, lon=77.59, capacity=600, stock=200,
               production_capacity=550, shifts_per_day=2)
WAREHOUSE = dict(name="Nagpur Hub", kind="warehouse", city="Nagpur", lat=21.15, lon=79.09, capacity=600, stock=300, storage_capacity=5000)
RETAILER = dict(name="Mumbai Store", kind="retailer", city="Mumbai", lat=19.08, lon=72.88, capacity=300, stock=100,
                daily_demand=150, shelf_stock=50, service_level_pct=95)
CUSTOMER = dict(name="Delhi Buyer", kind="customer", city="Delhi", lat=28.70, lon=77.10, stock=200, daily_demand=120, priority="high")


@pytest.fixture(autouse=True)
def clean_store():
    store.use_preset()
    store.reset("empty")
    cache.clear()
    yield
    store.use_preset()
    store.reset("empty")
    cache.clear()


def add_node(body: dict) -> str:
    r = client.post("/network/nodes", json=body)
    assert r.status_code == 201, r.text
    return r.json()["node"]["id"]


def add_edge(src: str, dst: str, **kw) -> dict:
    r = client.post("/network/edges", json={"source": src, "target": dst, "capacity": kw.pop("capacity", 500), **kw})
    assert r.status_code == 201, r.text
    return r.json()["edge"]


def build_full() -> dict[str, str]:
    """2 suppliers (1 backup), factory, warehouse, retailer, customer; retailer also ships to the customer."""
    ids = {k: add_node(v) for k, v in
           {"S": SUPPLIER, "B": BACKUP, "F": FACTORY, "W": WAREHOUSE, "R": RETAILER, "C": CUSTOMER}.items()}
    for s, t in [("S", "F"), ("B", "F"), ("F", "W"), ("W", "R"), ("R", "C"), ("W", "C")]:
        add_edge(ids[s], ids[t])
    return ids


def activate():
    r = client.put("/network/source", json={"source": "manual"})
    assert r.status_code == 200, r.text
    return r.json()


def codes(report: dict, key: str) -> set[str]:
    return {i["code"] for i in report[key]}


# ---------------------------------------------------------------- CRUD
def test_create_update_delete_node():
    nid = add_node(SUPPLIER)
    assert nid == "S1"
    assert add_node(SUPPLIER) == "S2"  # ids auto-increment per type prefix
    r = client.put(f"/network/nodes/{nid}", json={**SUPPLIER, "name": "Pune Steel Coils", "capacity": 900})
    assert r.status_code == 200 and r.json()["node"]["capacity"] == 900 and r.json()["node"]["name"] == "Pune Steel Coils"
    r = client.delete(f"/network/nodes/{nid}")
    assert r.status_code == 200 and r.json()["node"]["id"] == nid
    assert [n["id"] for n in client.get("/network/manual").json()["nodes"]] == ["S2"]
    assert client.delete(f"/network/nodes/{nid}").status_code == 404
    assert client.put("/network/nodes/NOPE", json=SUPPLIER).status_code == 404


def test_id_is_editable_only_on_create():
    assert add_node({**SUPPLIER, "id": "PUNE1"}) == "PUNE1"
    r = client.post("/network/nodes", json={**SUPPLIER, "id": "PUNE1"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "id"]
    r = client.put("/network/nodes/PUNE1", json={**SUPPLIER, "id": "OTHER"})
    assert r.status_code == 422 and "only be set when the node is created" in r.text


def test_create_update_delete_edge_with_suggestions():
    s, f = add_node(SUPPLIER), add_node(FACTORY)
    e = add_edge(s, f, mode="rail")
    assert e["id"] == "E1" and e["distance_km"] > 700 and e["lead"] >= 1 and e["co2"] > 0 and e["cost"] > 0
    road = client.put(f"/network/edges/{e['id']}", json={"source": s, "target": f, "capacity": 300, "mode": "road"}).json()["edge"]
    assert road["capacity"] == 300 and road["co2"] > e["co2"]  # road emits more than rail
    custom = client.put(f"/network/edges/{e['id']}", json={"source": s, "target": f, "capacity": 300, "distance_km": 10, "lead": 9}).json()["edge"]
    assert custom["distance_km"] == 10 and custom["lead"] == 9  # overrides win
    assert client.delete(f"/network/edges/{e['id']}").status_code == 200
    assert client.get("/network/manual").json()["edges"] == []
    assert client.delete(f"/network/edges/{e['id']}").status_code == 404


def test_delete_node_cascades_to_its_lanes():
    ids = build_full()
    r = client.delete(f"/network/nodes/{ids['W']}")
    removed = {(e["source"], e["target"]) for e in r.json()["removed_edges"]}
    assert removed == {(ids["F"], ids["W"]), (ids["W"], ids["R"]), (ids["W"], ids["C"])}
    left = client.get("/network/manual").json()["edges"]
    assert all(ids["W"] not in (e["source"], e["target"]) for e in left) and len(left) == 3


# ---------------------------------------------------------------- field validation (422)
@pytest.mark.parametrize("body, field", [
    ({**SUPPLIER, "capacity": -1}, "capacity"),
    ({**SUPPLIER, "lat": 91}, "lat"),
    ({**SUPPLIER, "lon": -181}, "lon"),
    ({**SUPPLIER, "reliability": 1.5}, "reliability"),
    ({**SUPPLIER, "name": ""}, "name"),
    ({**SUPPLIER, "id": "bad id!"}, "id"),
    ({**SUPPLIER, "kind": "spaceship"}, "kind"),
    ({**CUSTOMER, "daily_demand": None}, "daily_demand"),
    ({**FACTORY, "overtime_limit_pct": 120}, "overtime_limit_pct"),
])
def test_node_field_errors_are_field_level(body, field):
    r = client.post("/network/nodes", json=body)
    assert r.status_code == 422
    assert any(d["loc"][-1] == field for d in r.json()["detail"]), r.text


def test_node_rejects_fields_of_another_type():
    r = client.post("/network/nodes", json={**SUPPLIER, "daily_demand": 10})
    assert r.status_code == 422 and "not used by a supplier" in r.text


@pytest.mark.parametrize("make, fragment", [
    (lambda s, f, c: {"source": s, "target": s, "capacity": 1}, "same node"),
    (lambda s, f, c: {"source": s, "target": "NOPE", "capacity": 1}, "Unknown node"),
    (lambda s, f, c: {"source": s, "target": c, "capacity": 1}, "cannot ship to a customer"),
    (lambda s, f, c: {"source": c, "target": s, "capacity": 1}, "cannot ship to a supplier"),
    (lambda s, f, c: {"source": s, "target": f, "capacity": -5}, "greater than or equal to 0"),
])
def test_edge_rejections(make, fragment):
    s, f, c = add_node(SUPPLIER), add_node(FACTORY), add_node(CUSTOMER)
    r = client.post("/network/edges", json=make(s, f, c))
    assert r.status_code == 422 and fragment in r.text


def test_duplicate_edge_rejected():
    s, f = add_node(SUPPLIER), add_node(FACTORY)
    add_edge(s, f)
    r = client.post("/network/edges", json={"source": s, "target": f, "capacity": 1})
    assert r.status_code == 422 and "already connects" in r.text


# ---------------------------------------------------------------- network validation rules
def test_validation_errors_block_activation():
    report = client.post("/network/validate").json()
    assert codes(report, "errors") == {"no_supplier", "no_demand"} and not report["runnable"]
    add_node(SUPPLIER)
    assert codes(client.post("/network/validate").json(), "errors") == {"no_demand"}
    r = client.put("/network/source", json={"source": "manual"})
    assert r.status_code == 409 and "retailer or customer" in r.json()["detail"]
    assert client.get("/network/source").json()["source"] == "preset"


def test_validation_of_a_draft_body():
    draft = {
        "nodes": [{**SUPPLIER, "id": "S1"}, {**SUPPLIER, "id": "S1"}, {**CUSTOMER, "id": "C1"}],
        "edges": [{"id": "E1", "source": "S1", "target": "X9", "capacity": 1},
                  {"id": "E2", "source": "S1", "target": "C1", "capacity": 1},
                  {"id": "E3", "source": "S1", "target": "C1", "capacity": 1}],
    }
    report = ValidationReport.model_validate(client.post("/network/validate", json=draft).json())
    assert {"duplicate_id", "missing_node", "duplicate_edge"} <= {i.code for i in report.errors}
    assert not report.runnable


def test_validation_warnings():
    s = add_node({**SUPPLIER, "capacity": 50})  # far below demand
    w = add_node({**WAREHOUSE, "stock": 9000, "storage_capacity": 100})  # over storage
    c = add_node(CUSTOMER)
    add_node(CUSTOMER)  # isolated
    lonely = add_node(RETAILER)  # unreachable: fed by nothing
    add_edge(s, w)
    add_edge(w, c)
    off = add_node({**FACTORY, "status": "inactive"})
    add_edge(s, off)  # lane to an inactive node is ignored
    client.post("/network/edges", json={"source": lonely, "target": c, "capacity": 5})
    report = client.post("/network/validate").json()
    assert report["runnable"] and report["errors"] == []
    assert {"isolated", "supply_shortfall", "no_backup", "over_storage", "inactive_endpoint"} <= codes(report, "warnings")
    unreachable = [i for i in report["warnings"] if i["code"] == "unreachable"]
    assert unreachable and unreachable[0]["refs"] == [lonely]


def test_illegal_direction_and_zero_demand_warnings_on_import():
    net = {"nodes": [{**SUPPLIER, "id": "S1"}, {**CUSTOMER, "id": "C1", "daily_demand": 0}],
           "edges": [{"id": "E1", "source": "S1", "target": "C1", "capacity": 10}]}
    r = client.post("/network/import", json=net)
    assert r.status_code == 200
    assert {"illegal_direction", "zero_demand"} <= codes(r.json()["validation"], "warnings")


def test_import_rejects_structural_problems_and_changes_nothing():
    add_node(SUPPLIER)
    bad = {"nodes": [{**SUPPLIER, "id": "A1"}, {**CUSTOMER, "id": "A1"}], "edges": []}
    r = client.post("/network/import", json=bad)
    assert r.status_code == 422 and "used more than once" in r.text
    assert [n["id"] for n in client.get("/network/manual").json()["nodes"]] == ["S1"]
    r = client.post("/network/import", params={"activate": True}, json={"nodes": [{**SUPPLIER, "id": "Z1"}], "edges": []})
    assert r.status_code == 409  # no demand node: not activated, and nothing replaced
    assert [n["id"] for n in client.get("/network/manual").json()["nodes"]] == ["S1"]


# ---------------------------------------------------------------- version + cache invalidation
def test_every_mutation_bumps_version_and_clears_caches():
    v0 = client.get("/network/source").json()["version"]
    s = add_node(SUPPLIER)
    c = add_node(CUSTOMER)
    w = add_node(WAREHOUSE)
    add_edge(s, w)
    e = add_edge(w, c)
    v1 = client.get("/network/source").json()["version"]
    assert v1 == v0 + 5
    activate()
    client.get("/chaos")
    assert cache._mem and chaos_core._SCAN_CACHE
    client.put(f"/network/edges/{e['id']}", json={"source": w, "target": c, "capacity": 50})
    assert not cache._mem and not chaos_core._SCAN_CACHE
    assert client.get("/network/source").json()["version"] == v1 + 2


def test_results_refresh_after_an_edit():
    ids = build_full()
    activate()
    before = client.get("/network").json()
    client.delete(f"/network/nodes/{ids['R']}")
    after = client.get("/network").json()
    assert len(after["nodes"]) == len(before["nodes"]) - 1
    assert all(ids["R"] not in (e["source"], e["target"]) for e in after["edges"])


# ---------------------------------------------------------------- engine on manual networks
def test_manual_network_with_retailers_runs_every_endpoint():
    ids = build_full()
    info = activate()
    assert info["source"] == "manual" and info["runnable"] and info["node_count"] == 6

    net = NetworkResponse.model_validate(client.get("/network").json())
    kinds = {n.id: n.kind for n in net.nodes}
    assert kinds[ids["R"]] == "retailer" and net.resilience_score is not None
    retailer = next(n for n in net.nodes if n.id == ids["R"])
    assert retailer.demand == 150 and retailer.stock == 150  # back-room + shelf
    assert retailer.details["service_level_pct"] == 95

    outage = [{"type": "node", "target": ids["S"], "start": 2, "duration": 8, "severity": 1}]
    sim = SimulateResponse.model_validate(client.post("/simulate", json={"events": outage}).json())
    assert sim.total_unmet > 0 and ids["R"] in sim.delay.per_customer and ids["C"] in sim.delay.per_customer
    assert sim.survival_clock_days < 30
    spike = [{"type": "demand", "target": ids["R"], "start": 1, "duration": 5, "severity": 0.5}]
    assert client.post("/simulate", json={"events": spike}).status_code == 200  # a retailer is a valid demand target
    bad = [{"type": "demand", "target": ids["S"], "start": 1, "duration": 5, "severity": 0.5}]
    assert client.post("/simulate", json={"events": bad}).status_code == 422

    MonteCarloResponse.model_validate(client.post("/montecarlo", json={"events": outage, "n": 20}).json())
    chaos = ChaosResponse.model_validate(client.get("/chaos").json())
    assert chaos.spof and all(s.target not in (ids["R"], ids["C"]) for s in chaos.spof)  # demand nodes are not targets
    rec = RecoverResponse.model_validate(client.post("/recover", json={"events": outage}).json())
    assert sum(s.recommended for s in rec.strategies) == 1
    assert rec.alternate_suppliers and rec.alternate_suppliers[0].supplier == ids["B"]
    fc = ForecastResponse.model_validate(client.get("/forecast").json())
    assert {c.id for c in fc.customers} == {ids["R"], ids["C"]}


def test_minimal_network_one_supplier_one_customer():
    s, c = add_node(SUPPLIER), add_node(CUSTOMER)
    w = add_node(WAREHOUSE)
    add_edge(s, w)
    add_edge(w, c)
    client.delete(f"/network/nodes/{w}")  # back to 2 nodes, no lane
    r = client.post("/network/import", json={"nodes": [{**SUPPLIER, "id": "S1"}, {**CUSTOMER, "id": "C1"}],
                                             "edges": []}, params={"activate": True})
    assert r.status_code == 200
    net = NetworkResponse.model_validate(client.get("/network").json())
    assert all(n.risk is None and n.risk_note for n in net.nodes)  # too small for the model: null, not a crash
    ev = [{"type": "node", "target": "S1", "start": 0, "duration": 3, "severity": 1}]
    sim = client.post("/simulate", json={"events": ev})
    assert sim.status_code == 200 and sim.json()["total_unmet"] > 0  # disconnected: everything goes unmet
    assert client.get("/chaos").status_code == 200
    assert client.post("/recover", json={"events": ev}).status_code == 200


def test_minimal_connected_network_via_direct_lane():
    r = client.post("/network/import", params={"activate": True}, json={
        "nodes": [{**SUPPLIER, "id": "S1"}, {**FACTORY, "id": "F1"}, {**CUSTOMER, "id": "C1"}],
        "edges": [{"source": "S1", "target": "F1", "capacity": 500}, {"source": "F1", "target": "C1", "capacity": 500}],
    })
    assert r.status_code == 200
    ev = [{"type": "edge", "target": "F1->C1", "start": 1, "duration": 3, "severity": 1}]
    assert SimulateResponse.model_validate(client.post("/simulate", json={"events": ev}).json()).total_unmet > 0
    assert client.get("/chaos").json()["spof"]
    assert client.post("/recover", json={"events": ev}).status_code == 200


def test_disconnected_demand_node():
    ids = build_full()
    lonely = add_node({**CUSTOMER, "name": "Island", "lat": 11.6, "lon": 92.7})
    activate()
    warn = [i for i in client.get("/network/manual").json()["validation"]["warnings"] if i["code"] == "isolated"]
    assert warn and warn[0]["refs"] == [lonely]
    sim = client.post("/simulate", json={"events": [{"type": "node", "target": ids["F"], "start": 1, "duration": 2, "severity": 0.5}]}).json()
    assert sim["stockout_day"].get(lonely) is not None  # never served: stocks out once its own stock runs dry
    chaos = client.get("/chaos")
    assert chaos.status_code == 200 and all(s["target"] != lonely for s in chaos.json()["spof"])


def test_empty_network_gives_clean_messages():
    r = client.put("/network/source", json={"source": "manual"})
    assert r.status_code == 409
    ids = build_full()
    activate()
    for nid in ids.values():
        client.delete(f"/network/nodes/{nid}")
    body = client.get("/network").json()
    assert body["nodes"] == [] and body["resilience_score"] is None
    for r in (client.post("/simulate", json={"events": [{"type": "node", "target": "S1", "start": 0, "duration": 1, "severity": 1}]}),
              client.get("/chaos"),
              client.post("/recover", json={"events": [{"type": "node", "target": "S1", "start": 0, "duration": 1, "severity": 1}]})):
        assert r.status_code == 409 and "Data tab" in r.json()["detail"]
    assert client.get("/forecast").json()["customers"] == []


# ---------------------------------------------------------------- import / export / reset / sources
def test_export_import_round_trip():
    build_full()
    exported = client.get("/network/export").json()
    assert exported["format"] == "aegis-network" and len(exported["nodes"]) == 6 and len(exported["edges"]) == 6
    client.post("/network/reset", params={"to": "empty"})
    assert client.get("/network/manual").json()["nodes"] == []
    r = client.post("/network/import", json=exported)
    assert r.status_code == 200
    again = client.get("/network/export").json()
    assert again["nodes"] == exported["nodes"] and again["edges"] == exported["edges"]


def test_csv_export_is_accepted_by_the_csv_importer():
    build_full()
    nodes_csv = client.get("/network/export/csv", params={"file": "nodes"})
    edges_csv = client.get("/network/export/csv", params={"file": "edges"})
    assert nodes_csv.headers["content-type"].startswith("text/csv") and "retailer" in nodes_csv.text
    files = {"nodes": ("n.csv", nodes_csv.content, "text/csv"), "edges": ("e.csv", edges_csv.content, "text/csv")}
    r = client.post("/upload", files=files)
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["by_kind"] == {"customer": 1, "factory": 1, "retailer": 1, "supplier": 2, "warehouse": 1}


def test_reset_to_preset_copies_preset_into_builder():
    r = client.post("/network/reset", params={"to": "preset"})
    assert r.status_code == 200 and r.json()["source"] == "preset"
    assert len(r.json()["nodes"]) == len(client.get("/network").json()["nodes"]) == 16
    assert r.json()["validation"]["runnable"]
    assert client.put("/network/source", json={"source": "manual"}).status_code == 200


def test_switch_to_preset_and_back_keeps_manual_network():
    ids = build_full()
    activate()
    assert len(client.get("/network").json()["nodes"]) == 6
    client.put("/network/source", json={"source": "preset"})
    assert client.get("/chaos").json()["resilience_score"] == 62.4  # mocked preset again
    assert len(client.get("/network").json()["nodes"]) == 16
    activate()
    assert {n["id"] for n in client.get("/network").json()["nodes"]} == set(ids.values())


def test_csv_source_requires_an_upload():
    r = client.put("/network/source", json={"source": "csv"})
    assert r.status_code == 409 and "CSV" in r.json()["detail"]


def test_csv_upload_and_preset_unchanged():
    files = {"nodes": ("n.csv", (MOCK_DIR / "sample_nodes.csv").read_bytes(), "text/csv"),
             "edges": ("e.csv", (MOCK_DIR / "sample_edges.csv").read_bytes(), "text/csv")}
    r = client.post("/upload", files=files)
    assert r.status_code == 200 and r.json()["activated"] is False
    assert client.get("/network/source").json()["source"] == "preset"
    r = client.post("/upload", params={"activate": True}, files=files)
    assert r.json()["activated"] is True and client.get("/network/source").json()["source"] == "csv"
    ev = [{"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1}]
    assert client.post("/simulate", json={"events": ev}).status_code == 200  # live engine on the uploaded network
    client.put("/network/source", json={"source": "preset"})
    assert client.get("/chaos").json()["resilience_score"] == 62.4


def test_source_info_shape():
    info = client.get("/network/source").json()
    assert set(info) >= {"source", "version", "node_count", "edge_count"} and info["source"] == "preset"


# ---------------------------------------------------------------- persistence
def test_persisted_network_survives_a_restart(tmp_path):
    path = tmp_path / "active_network.json"
    s1 = NetworkStore(path)
    s1.add_node({**SUPPLIER, "id": "S1"})
    s1.add_node({**WAREHOUSE, "id": "W1"})
    s1.add_node({**CUSTOMER, "id": "C1"})
    s1.add_edge({"source": "S1", "target": "W1", "capacity": 100})
    s1.add_edge({"source": "W1", "target": "C1", "capacity": 100})
    s1.set_source("manual")
    s2 = NetworkStore(path)
    assert s2.source == "manual" and s2.version == s1.version and set(s2.nodes) == {"S1", "W1", "C1"}
    assert s2.graph().number_of_edges() == 2 and s2.note is None


@pytest.mark.parametrize("content", ["{not json", json.dumps({"format": "something-else"}),
                                     json.dumps({"format": "aegis-active-network", "source": "manual",
                                                 "manual": {"nodes": [{"id": "S1", "kind": "supplier"}]}})])
def test_corrupt_persisted_file_falls_back_to_preset(tmp_path, content):
    path = tmp_path / "active_network.json"
    path.write_text(content, encoding="utf-8")
    s = NetworkStore(path)
    assert s.source == "preset" and s.nodes == {} and s.note and "preset" in s.note
    assert (tmp_path / "active_network.corrupt.json").exists()


def test_missing_file_starts_on_preset(tmp_path):
    s = NetworkStore(tmp_path / "nope" / "active_network.json")
    assert s.source == "preset" and s.note is None


# ---------------------------------------------------------------- error handling
def test_unhandled_errors_return_json_not_a_stack_trace(monkeypatch):
    from core import chaos as chaos_mod

    ids = build_full()
    activate()

    def boom(*_a, **_k):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(chaos_mod, "chaos_find", boom)
    safe = TestClient(app, raise_server_exceptions=False)
    r = safe.get("/chaos")
    assert r.status_code == 500 and r.json()["detail"].startswith("Internal error") and "Traceback" not in r.text
    assert ids  # network untouched

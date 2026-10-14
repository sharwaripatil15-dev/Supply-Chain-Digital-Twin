"""Run the real AEGIS engine on the sample network and export scenario results for docs/twin-data.js.

usage: backend/.venv/Scripts/python.exe docs/tools/export_twin.py   (writes docs/twin-data.js)
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "..", "backend"))
OUT = os.path.normpath(os.path.join(HERE, "..", "twin-data.js"))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from core.graph import load_network_from_csv
from core.sim import simulate
from core.chaos import chaos_find
from core.strategies import run_strategies
from schemas import Event

G, _ = load_network_from_csv("mock/sample_nodes.csv", "mock/sample_edges.csv")
nodes = list(csv.DictReader(open("mock/sample_nodes.csv")))
edges = list(csv.DictReader(open("mock/sample_edges.csv")))

SCEN = [
    ("f1", "Bengaluru Assembly (F1) shuts for 10 days", [Event(type="node", target="F1", start=0, duration=10, severity=1.0)]),
    ("w3", "Flood closes Sriperumbudur DC (W3) for 7 days", [Event(type="node", target="W3", start=0, duration=7, severity=1.0)]),
    ("pair", "Hidden pair: F1 and F2 both down for 10 days", [Event(type="node", target="F1", start=0, duration=10, severity=1.0),
                                                              Event(type="node", target="F2", start=0, duration=10, severity=1.0)]),
    ("spike", "Festival spike: Delhi + Jaipur demand +80% for 7 days", [Event(type="demand", target="C2", start=1, duration=7, severity=0.8),
                                                                       Event(type="demand", target="C5", start=1, duration=7, severity=0.8)]),
    ("s2", "Chennai Electronics (S2) fails for 10 days", [Event(type="node", target="S2", start=0, duration=10, severity=1.0)]),
]
out = {"nodes": nodes, "edges": edges, "scenarios": []}
for sid, title, ev in SCEN:
    r = simulate(G, ev, horizon=14)
    strategies = []
    for s in run_strategies(G, ev, horizon=14):
        strategies.append({k: s[k] for k in ("name", "cost", "unmet", "recovery_days", "co2", "recommended")} | {"safe": s["safety_check"]["passed"]})
    out["scenarios"].append({
        "id": sid, "title": title,
        "events": [{"type": e.type, "target": e.target, "start": e.start, "duration": e.duration, "severity": e.severity} for e in ev],
        "timeline": [{"day": d["day"], "unmet": round(d["unmet"]), "status": d["node_status"]} for d in r["timeline"]],
        "total_unmet": r["total_unmet"], "survival_clock_days": r["survival_clock_days"],
        "revenue_at_risk": r["revenue_at_risk"], "stockout_day": r["stockout_day"], "log": r["log"][:12],
        "strategies": strategies,
    })
    print(sid, r["total_unmet"], r["survival_clock_days"])
out["chaos"] = chaos_find(G, top=5)
open(OUT, "w", encoding="utf-8").write(
    "// Generated from the real AEGIS engine (core.sim, core.chaos, core.strategies) on backend/mock/sample_*.csv\n"
    "window.AEGIS_DATA = " + json.dumps(out, indent=1) + ";\n")

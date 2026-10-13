"""Manual end-to-end check of weather-aware routing against a running AEGIS API.

    python scripts/weather_e2e.py [--url http://localhost:8000] [--horizon 7]

For each built-in scenario: activate it, then /weather/risk -> /weather/apply -> /simulate -> /weather/reroute ->
/weather/chaos, print what happened (blocked routes, recommended alternatives, delay saved, safety warnings) and check
the scenario's `expected` assertions. Finally switch back to Live mode and report data quality (run it once online and
once offline to see the cached / unavailable fallback). Leaves the server in Live mode with no weather events applied.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.hazards import simulated as sim_hz  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def graph_from(network: dict) -> nx.DiGraph:
    G = nx.DiGraph()
    for n in network["nodes"]:
        G.add_node(n["id"], **n)
    for e in network["edges"]:
        G.add_edge(e["source"], e["target"], **e)
    return G


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--horizon", type=int, default=7)
    args = ap.parse_args()
    c = httpx.Client(base_url=args.url, timeout=120)
    G = graph_from(c.get("/network").json())
    scenarios = c.get("/weather/simulated-scenarios").json()["scenarios"]
    failures = 0
    for s in scenarios:
        print(f"\n=== {s['label']} ===")
        c.post("/weather/simulated-scenarios", json={"id": s["id"]}).raise_for_status()
        risk = c.get("/weather/risk", params={"horizon": args.horizon}).json()
        summ = risk["summary"]
        print(f"data quality: {risk['data_quality']}; high-risk lanes {summ['high_risk_edges']}, closed {summ['closed_edges']}, "
              f"sites hit {summ['affected_nodes']}")
        for m in risk["mapping"]:
            print(f"  mapping: {m['wanted']} -> {', '.join(m['matched'] or ['-'])} ({m['how']})" + (f"; {m['note']}" if m.get("note") else ""))
        applied = c.post("/weather/apply", json={"horizon": args.horizon}).json()
        print(f"apply: {applied['summary']}")
        sim = c.post("/simulate", json={"events": applied["events"], "horizon": 30})
        if sim.status_code == 200:
            body = sim.json()
            print(f"simulate: unmet {body['total_unmet']:,.0f} units, stock-out in {body['survival_clock_days']} days, "
                  f"avg delay {body['delay']['avg_days']} days")
        else:
            print(f"simulate: HTTP {sim.status_code} {sim.text[:200]}")
        rr = c.post("/weather/reroute", json={"horizon": args.horizon, "events": applied["events"]}).json()
        print(f"reroute: {rr['summary']['blocked']} blocked, {rr['summary']['rerouted']} rerouted, "
              f"~{rr['summary']['delay_saved_days']} days of delay saved; headline: {rr['summary']['headline']}")
        for o in rr["options"]:
            rec = next((a for a in o["alternatives"] if a["recommended"]), None)
            warn = [a for a in o["alternatives"] if not a["safety_check"]["passed"]]
            print(f"  - {o['blocked_edge']} days {o['window'][0]}-{o['window'][1]} ({o['level']}{', closed' if o['closed'] else ''}): "
                  f"{o['recommended_action']}" + (f" -> {' > '.join(rec['path'])} [{rec['mode']}], ETA {rec['eta_delta']:+.1f} d, "
                                                  f"cost {rec['cost_delta']:+.0f}/unit" if rec else ""))
            for a in warn[:1]:
                print(f"      safety warning on {' > '.join(a['path'])}: {a['safety_check']['warning']}")
        for a in rr.get("node_actions", []):
            print(f"  - site {a['node']}: {a['action']}" + (f" -> {a['to']}" if a.get("to") else ""))
        plan = rr.get("applied_strategy_summary")
        if plan:
            print(f"plan '{plan['name']}': unmet {plan['unmet']:,.0f} (do nothing {plan['do_nothing']['unmet']:,.0f}), "
                  f"cost {plan['cost']:,.0f} INR, safety {'passed' if plan['safety_check']['passed'] else 'FAILED'}")
        chaos = c.get("/weather/chaos", params={"horizon": args.horizon}).json()
        print(f"chaos: {chaos.get('detail')}")
        for r in sim_hz.check_expected(sim_hz.get_scenario(s["id"]), G, risk, rr, chaos):
            failures += not r["passed"]
            print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['check']}: {r['detail']}")

    print("\n=== Live mode ===")
    c.post("/weather/simulated-scenarios", json={"id": None})
    c.delete("/weather/apply")
    live = c.get("/weather/risk", params={"horizon": args.horizon}).json()
    print(f"data quality: {live['data_quality']}; high-risk lanes {live['summary']['high_risk_edges']}")
    for w in live["warnings"]:
        print(f"  warning: {w}")
    for p in c.get("/weather/status").json()["providers"]:
        print(f"  {p['provider']:8s} ok={p['ok']} quality={p['quality']} cache_age_s={p['cache_age_s']} error={p['last_error']}")
    print(f"\n{'All scenario checks passed.' if not failures else f'{failures} scenario check(s) failed.'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

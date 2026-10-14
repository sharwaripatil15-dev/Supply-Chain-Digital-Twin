"""Ready-made demo networks and the "Generate random network" action (both load through the Manual Builder import).

Each demo is a fixed generator call, so it is identical on every machine.
"""
from __future__ import annotations

from core.synth.networks import generate_network, to_builder
from core.synth.profiles import ARCHETYPE_LABEL, ARCHETYPES, INDUSTRIES

DEMOS = {
    "fmcg": {"label": "FMCG distribution", "archetype": "hub_spoke", "industry": "fmcg", "n_nodes": 30, "seed": 11,
             "blurb": "Hub-and-spoke soaps and staples network: plants feed two regional hubs that serve 20+ retailers."},
    "pharma": {"label": "Pharma cold-chain", "archetype": "backup_supplier", "industry": "pharma", "n_nodes": 24, "seed": 5,
               "blurb": "Temperature-controlled API and vial supply with a contracted backup supplier and air lanes."},
    "electronics": {"label": "Electronics, two regions + port", "archetype": "two_region_port", "industry": "electronics",
                    "n_nodes": 32, "seed": 3, "blurb": "Two manufacturing regions that share one port DC for finished goods."},
}


def options() -> dict:
    return {
        "demos": [{"id": k, **{f: v[f] for f in ("label", "archetype", "industry", "n_nodes", "blurb")}} for k, v in DEMOS.items()],
        "archetypes": [{"id": a, "label": ARCHETYPE_LABEL[a]} for a in ARCHETYPES],
        "industries": [{"id": k, "label": p.label} for k, p in INDUSTRIES.items()],
        "size": {"min": 10, "max": 60},
    }


def builder_payload(archetype: str, industry: str, n_nodes: int, seed: int, label: str | None = None) -> dict:
    G = generate_network(archetype, industry, n_nodes, seed)
    nodes, edges = to_builder(G)
    return {"nodes": nodes, "edges": edges, "meta": {
        "label": label or f"{INDUSTRIES[industry].label} - {ARCHETYPE_LABEL[archetype]} ({len(nodes)} nodes)",
        "archetype": archetype, "industry": industry, "n_nodes": len(nodes), "n_edges": len(edges), "seed": seed,
        "unit_price": G.graph["unit_price"], "month": G.graph["month"], "seasonal_factor": G.graph["seasonal_factor"]}}


def demo_payload(demo_id: str) -> dict:
    d = DEMOS[demo_id]
    return builder_payload(d["archetype"], d["industry"], d["n_nodes"], d["seed"], d["label"])

"""Dataset builder: run the EXACT simulator (core.sim.simulate) for every network x disruption and store the outcomes.

    python -m core.synth.build --n-networks 400 --cases-per-network 60 --seed 42          # full (24,000 rows)
    python -m core.synth.build --fast                                                    # small set for tests

Network i is generated from (seed, i): archetype = ARCHETYPES[i mod 7] and industry = INDUSTRIES[(i div 7) mod 6]
(balanced), size uniform in 10..60 (10..20 with --fast). Each case draws a disruption type uniformly from the library
(core.synth.disruptions), runs core.sim.simulate over HORIZON days and records:

    unmet_units      total unmet demand over the horizon (units)
    unmet_pct        unmet_units / (total daily demand x horizon) x 100
    avg_delay        extra delivery delay, mean over delivered units (days)  [core.delay]
    p90_delay        P90 of the same (days)
    stockout_day     first day any demand node runs out (horizon if none)    [Survival Clock]
    recovery_days    last day with unmet demand - disruption start + 1 (0 if none; censored at the horizon)
    peak_util        highest daily utilisation of any site over the horizon
    revenue_at_risk  unmet_units x unit price (INR)
plus every core.features.SCENARIO_FEATURES column, the metadata (network_id, archetype, industry, n_nodes,
disruption, region) and sim_ms (exact simulator wall time).

Split: networks (not rows) are assigned to train / val / calib / test = 60 / 10 / 10 / 20 % with a seeded
permutation, so no network appears in two splits. Output: data/synth/dataset[_fast].parquet + DATA_CARD[_fast].md.
Networks are built in parallel with joblib (one task per network).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

HORIZON = 30
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synth"
SPLIT_SHARES = (("train", 0.6), ("val", 0.1), ("calib", 0.1), ("test", 0.2))
TARGETS = ["unmet_pct", "avg_delay", "stockout_day", "recovery_days"]
OUTCOMES = ["unmet_units", "unmet_pct", "avg_delay", "p90_delay", "stockout_day", "recovery_days", "peak_util",
            "revenue_at_risk"]
META = ["network_id", "archetype", "industry", "n_nodes", "disruption", "region", "split", "sim_ms"]


def network_spec(seed: int, i: int, fast: bool) -> tuple[str, str, int, int]:
    from core.synth.profiles import ARCHETYPES, INDUSTRY_KEYS

    rng = np.random.default_rng([seed, i])
    lo, hi = (10, 20) if fast else (10, 60)
    return ARCHETYPES[i % len(ARCHETYPES)], INDUSTRY_KEYS[(i // len(ARCHETYPES)) % len(INDUSTRY_KEYS)], int(rng.integers(lo, hi + 1)), int(seed * 100_003 + i)


def outcomes(G, result: dict, events, horizon: int = HORIZON) -> dict:
    """The stored labels for one exact simulation (see the module docstring)."""
    from node_types import total_demand

    total = total_demand(G) * horizon
    start = min((e.start for e in events), default=0)
    last = result.get("last_unmet_day")
    peak = max((u for row in result["timeline"] for n, u in row["utilization"].items()
                if G.nodes[n]["kind"] in ("supplier", "factory", "warehouse")), default=0.0)
    return {
        "unmet_units": float(result["total_unmet"]),
        "unmet_pct": 100.0 * result["total_unmet"] / total if total else 0.0,
        "avg_delay": float(result["delay"]["avg_days"]),
        "p90_delay": float(result["delay"]["p90_days"]),
        "stockout_day": float(result["survival_clock_days"]),
        "recovery_days": float(max(0, last - start + 1)) if last is not None else 0.0,
        "peak_util": float(peak),
        "revenue_at_risk": float(result["revenue_at_risk"]),
    }


def build_network_rows(seed: int, i: int, cases: int, fast: bool) -> list[dict]:
    """Generate network i and simulate `cases` disruptions on it (one joblib task)."""
    from core.features import FeatureContext, scenario_features
    from core.sim import simulate
    from core.synth.disruptions import sample_disruption
    from core.synth.networks import generate_network

    archetype, industry, n, net_seed = network_spec(seed, i, fast)
    G = generate_network(archetype, industry, n, net_seed)
    ctx = FeatureContext(G)
    rng = np.random.default_rng([seed, i, 1])
    rows = []
    for _ in range(cases):
        d = sample_disruption(G, rng, horizon=HORIZON)
        t = time.perf_counter()
        res = simulate(G, d["events"], HORIZON)
        sim_ms = (time.perf_counter() - t) * 1000
        rows.append({
            **scenario_features(ctx, d["events"], d["type"], HORIZON), **outcomes(G, res, d["events"]),
            "network_id": i, "archetype": archetype, "industry": industry, "n_nodes": n, "disruption": d["type"],
            "region": d["region"], "sim_ms": sim_ms,
            "events_json": json.dumps([e.model_dump(exclude_none=True) for e in d["events"]]),
        })
    return rows


def assign_splits(network_ids, seed: int) -> dict[int, str]:
    ids = np.array(sorted(set(network_ids)))
    perm = np.random.default_rng(seed).permutation(ids)
    out, at = {}, 0
    for k, (name, share) in enumerate(SPLIT_SHARES):
        n = len(perm) - at if k == len(SPLIT_SHARES) - 1 else max(1, int(round(share * len(perm))))
        out.update({int(x): name for x in perm[at:at + n]})
        at += n
    return out


def build(n_networks: int = 400, cases: int = 60, seed: int = 42, fast: bool = False, jobs: int = -1,
          out_dir: Path = DATA_DIR, verbose: bool = True) -> pd.DataFrame:
    from joblib import Parallel, delayed

    t0 = time.perf_counter()
    chunks = Parallel(n_jobs=jobs, verbose=5 if verbose else 0)(
        delayed(build_network_rows)(seed, i, cases, fast) for i in range(n_networks))
    df = pd.DataFrame([r for c in chunks for r in c])
    splits = assign_splits(df["network_id"], seed)
    df["split"] = df["network_id"].map(splits)
    elapsed = time.perf_counter() - t0
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_fast" if fast else ""
    path = out_dir / f"dataset{suffix}.parquet"
    df.to_parquet(path, index=False)
    (out_dir / f"DATA_CARD{suffix}.md").write_text(data_card(df, seed, fast, elapsed, path.name), encoding="utf-8")
    if verbose:
        print(f"{len(df):,} rows from {n_networks} networks in {elapsed:.0f}s -> {path}")
    return df


def data_card(df: pd.DataFrame, seed: int, fast: bool, elapsed: float, file: str) -> str:
    """Markdown data card: provenance, composition, split, label distribution."""
    nets = df.groupby("split")["network_id"].nunique()
    rows = df.groupby("split").size()
    lines = [
        f"# Data card: synthetic disruption outcomes{' (fast)' if fast else ''}",
        "",
        f"* File: `data/synth/{file}`, {len(df):,} rows x {df.shape[1]} columns, {df['network_id'].nunique()} networks, "
        f"seed {seed}, built in {elapsed:.0f} s.",
        "* Labels: the AEGIS exact simulator (core.sim.simulate, 30-day horizon, daily min-cost flow, stock buffers, "
        "backup activation lag). They are **simulated outcomes, not real-world observations**.",
        "* Generator: core.synth (assumptions in data/synth_assumptions.md). Features: core.features.SCENARIO_FEATURES.",
        "* Split: grouped by network (no network in two splits).",
        "",
        "| split | networks | rows |",
        "|---|---:|---:|",
        *[f"| {s} | {nets.get(s, 0)} | {rows.get(s, 0):,} |" for s, _ in SPLIT_SHARES],
        "",
        "## Composition",
        "",
        "| archetype | rows | | industry | rows | | disruption | rows |",
        "|---|---:|---|---|---:|---|---|---:|",
    ]
    a = df["archetype"].value_counts().sort_index()
    ind = df["industry"].value_counts().sort_index()
    dis = df["disruption"].value_counts().sort_index()
    for i in range(max(len(a), len(ind), len(dis))):
        cell = lambda s: (f"{s.index[i]} | {s.iloc[i]:,}" if i < len(s) else " | ")  # noqa: E731
        lines.append(f"| {cell(a)} | | {cell(ind)} | | {cell(dis)} |")
    lines += ["", "## Labels", "", "| outcome | mean | P10 | P50 | P90 | max | share > 0 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for c in OUTCOMES:
        v = df[c]
        lines.append(f"| {c} | {v.mean():.2f} | {v.quantile(.1):.2f} | {v.median():.2f} | {v.quantile(.9):.2f} | "
                     f"{v.max():.2f} | {(v > 0).mean():.0%} |")
    lines += ["", f"Network size: {df['n_nodes'].min()}-{df['n_nodes'].max()} nodes. Exact simulator: "
                  f"{df['sim_ms'].mean():.0f} ms per case on average (P90 {df['sim_ms'].quantile(.9):.0f} ms).", ""]
    return "\n".join(lines)


def load_dataset(fast: bool = False) -> pd.DataFrame | None:
    path = DATA_DIR / f"dataset{'_fast' if fast else ''}.parquet"
    return pd.read_parquet(path) if path.exists() else None


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--n-networks", type=int, default=400)
    p.add_argument("--cases-per-network", type=int, default=60)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--fast", action="store_true", help="small networks and few cases (tests, auto-training)")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--out", type=Path, default=DATA_DIR)
    a = p.parse_args(argv)
    n, c = (a.n_networks, a.cases_per_network)
    if a.fast and n == 400 and c == 60:
        n, c = 42, 20
    build(n, c, a.seed, a.fast, a.jobs, a.out)


if __name__ == "__main__":
    main()

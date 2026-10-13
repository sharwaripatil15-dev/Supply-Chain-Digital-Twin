"""Customer demand forecasting. Owner: D.

History: a seeded synthetic daily series per customer (28 days): base demand x (1 + weekly seasonality) + small trend
+ noise. The seed comes from the graph seed and the customer id, so a network always has the same history.
Model: additive Holt-Winters exponential smoothing (level, trend, weekly season), smoothing parameters chosen by
grid search on one-step-ahead squared error. Bands: P10/P90 = mean -/+ 1.2816 x residual sd x sqrt(1 + (h-1) x alpha^2).
Backtest: refit on all but the last 7 days, forecast those 7, report MAPE averaged over customers.
The forecast is the demand baseline for demand-spike scenarios in core.sim and core.optimizer: during a spike,
customer demand on day t = forecast mean for day t x (1 + severity).
"""
from __future__ import annotations

import itertools
import zlib

import networkx as nx
import numpy as np

SEASON = 7
HISTORY_DAYS = 28
BACKTEST_DAYS = 7
Z90 = 1.2816
ALPHAS = (0.1, 0.2, 0.3, 0.5, 0.7)
BETAS = (0.01, 0.05, 0.1)
GAMMAS = (0.05, 0.1, 0.3)

_CACHE: dict[tuple, dict] = {}


def _customers(G: nx.DiGraph) -> list[str]:
    return [n for n, d in G.nodes(data=True) if d["kind"] == "customer"]


def demand_history(G: nx.DiGraph, days: int = HISTORY_DAYS, seed: int | None = None) -> dict[str, np.ndarray]:
    """{customer_id: demand for days -days+1 .. 0} (seeded synthetic series)."""
    seed = G.graph.get("seed", 7) if seed is None else seed
    out = {}
    for c in _customers(G):
        rng = np.random.default_rng([seed, zlib.crc32(c.encode())])
        base = G.nodes[c]["demand"]
        amp, phase = rng.uniform(0.08, 0.15), rng.integers(0, SEASON)
        trend = base * rng.uniform(-0.002, 0.004)
        d = np.arange(-days + 1, 1)
        out[c] = base * (1 + amp * np.sin(2 * np.pi * (d + phase) / SEASON)) + trend * d + rng.normal(0, 0.05 * base, days)
    return out


def _holt_winters(y: np.ndarray, alpha: float, beta: float, gamma: float, m: int = SEASON):
    """Additive Holt-Winters. Returns (one-step fitted values from index m, final level, trend, seasonals)."""
    level = y[:m].mean()
    trend = (y[m:2 * m].mean() - y[:m].mean()) / m if len(y) >= 2 * m else 0.0
    season = list(y[:m] - level)
    fitted = []
    for t in range(m, len(y)):
        s = season[t % m]
        fitted.append(level + trend + s)
        prev_level = level
        level = alpha * (y[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        season[t % m] = gamma * (y[t] - level) + (1 - gamma) * s
    return np.array(fitted), level, trend, season


def fit(y: np.ndarray) -> dict:
    """Grid-search alpha/beta/gamma; return the fitted model state."""
    best = None
    for a, b, g in itertools.product(ALPHAS, BETAS, GAMMAS):
        fitted, level, trend, season = _holt_winters(y, a, b, g)
        sse = float(np.sum((y[SEASON:] - fitted) ** 2))
        if best is None or sse < best["sse"]:
            best = {"alpha": a, "beta": b, "gamma": g, "sse": sse, "level": level, "trend": trend,
                    "season": season, "n": len(y), "sd": float(np.std(y[SEASON:] - fitted))}
    return best


def predict(model: dict, horizon: int) -> np.ndarray:
    n, m = model["n"], SEASON
    return np.array([model["level"] + h * model["trend"] + model["season"][(n + h - 1) % m] for h in range(1, horizon + 1)])


def forecast_demand(G: nx.DiGraph, horizon: int = 14) -> dict:
    """GET /forecast shape: {horizon_days, method, mape, customers:[{id, history, forecast}]}."""
    from core.chaos import _fingerprint

    key = (_fingerprint(G), horizon)
    if key in _CACHE:
        return _CACHE[key]
    history = demand_history(G)
    customers, apes = [], []
    for c, y in history.items():
        back = fit(y[:-BACKTEST_DAYS])
        actual = y[-BACKTEST_DAYS:]
        apes.append(float(np.mean(np.abs(predict(back, BACKTEST_DAYS) - actual) / actual)))
        model = fit(y)
        mean = predict(model, horizon)
        spread = [Z90 * model["sd"] * np.sqrt(1 + (h - 1) * model["alpha"] ** 2) for h in range(1, horizon + 1)]
        customers.append({
            "id": c,
            "history": [{"day": int(d), "demand": round(float(v), 1)} for d, v in zip(range(-len(y) + 1, 1), y)],
            "forecast": [{"day": h, "mean": round(float(mu), 1), "p10": round(float(mu - s), 1), "p90": round(float(mu + s), 1)}
                         for h, mu, s in zip(range(1, horizon + 1), mean, spread)],
        })
    result = {"horizon_days": horizon, "method": "Holt-Winters additive, weekly season (fitted per customer)",
              "mape": round(float(np.mean(apes)), 4), "customers": customers}
    _CACHE[key] = result
    return result


def demand_ratio(G: nx.DiGraph, horizon: int = 30) -> dict[str, list[float]]:
    """{customer: [forecast mean / nominal demand for sim day 0..horizon-1]}: the demand-spike baseline."""
    fc = forecast_demand(G, horizon)
    return {c["id"]: [p["mean"] / G.nodes[c["id"]]["demand"] for p in c["forecast"]] for c in fc["customers"]}

"""Trend detection over term averages. Deterministic and explainable; no LLM.

Method: average the (outlier-free) scores within each term, then
  * Theil-Sen slope (median of pairwise slopes; robust to stray points),
  * Mann-Kendall test for a monotonic trend (normal approximation, no tie correction),
  * early-vs-late change (mean of the first third of terms vs the last third).
A trend is reported only if the test is significant AND the change is practically meaningful.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, median
from typing import Any

from app.mcp_server.analysis.common import term_label

ALPHA = 0.05        # significance level for Mann-Kendall
MIN_SLOPE = 0.5     # points per term; sanity floor on the Theil-Sen slope
MIN_CHANGE = 8.0    # points between early and late thirds; practical-significance floor


def theil_sen(xs: list[float], ys: list[float]) -> tuple[float, float]:
    slopes = [
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(len(xs))
        for j in range(i + 1, len(xs))
        if xs[j] != xs[i]
    ]
    if not slopes:
        return 0.0, (median(ys) if ys else 0.0)
    slope = median(slopes)
    intercept = median(y - slope * x for x, y in zip(xs, ys))
    return slope, intercept


def mann_kendall(ys: list[float]) -> dict[str, float]:
    n = len(ys)
    if n < 3:
        return {"S": 0.0, "z": 0.0, "p": 1.0}
    s = sum(
        (ys[j] > ys[i]) - (ys[j] < ys[i])
        for i in range(n - 1)
        for j in range(i + 1, n)
    )
    var = n * (n - 1) * (2 * n + 5) / 18.0
    z = 0.0 if s == 0 else (s - math.copysign(1, s)) / math.sqrt(var)  # continuity correction
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"S": float(s), "z": z, "p": p}


def term_means(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """rows need 'ord' and 'pct'. Returns one point per term that has data, in order."""
    by: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("pct") is not None:
            by[r["ord"]].append(r["pct"])
    return [{"ord": o, "term": term_label(o), "mean": mean(v), "n": len(v)} for o, v in sorted(by.items())]


def trend(points: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(points)
    xs = [float(p["ord"]) for p in points]   # real term positions, so gaps are respected
    ys = [p["mean"] for p in points]
    if n < 3:
        return {"n_terms": n, "slope": 0.0, "early_mean": None, "late_mean": None,
                "change": 0.0, "p_value": 1.0, "direction": "none"}
    slope, _ = theil_sen(xs, ys)
    k = max(2, n // 3)
    early, late = mean(ys[:k]), mean(ys[-k:])
    change = late - early
    p = mann_kendall(ys)["p"]
    direction = "none"
    if p < ALPHA and abs(slope) >= MIN_SLOPE and abs(change) >= MIN_CHANGE and slope * change > 0:
        direction = "up" if slope > 0 else "down"
    return {"n_terms": n, "slope": slope, "early_mean": early, "late_mean": late,
            "change": change, "p_value": p, "direction": direction}

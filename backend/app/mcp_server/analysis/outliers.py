"""Reject single anomalous scores before any trend is computed.

Within one skill, quizzes and coursework (assignments, projects) are assessed under different
conditions, so they are screened separately. Each group is detrended with a Theil-Sen line and a
point is flagged when its residual is both statistically extreme (robust z via MAD) and large in
absolute terms. Flagged points are reported, never silently dropped.
"""
from __future__ import annotations

from statistics import median
from typing import Any

from app.mcp_server.analysis.trends import theil_sen

MIN_GROUP = 8         # records needed in a group before screening it
Z_THRESHOLD = 3.5     # robust z-score
MIN_POINTS = 20.0     # and at least this many percentage points off the learner's own line
SCALE_FLOOR = 3.0     # stops a very tight group from flagging ordinary noise


def kind_class(kind: str) -> str:
    return "quiz" if kind == "quiz" else "coursework"


def detect_outliers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """rows need 'ord' and 'pct' (all one skill, one kind class). Returns flagged rows with
    'expected' and 'residual' added."""
    if len(rows) < MIN_GROUP:
        return []
    xs = [float(r["ord"]) for r in rows]
    ys = [r["pct"] for r in rows]
    slope, intercept = theil_sen(xs, ys)
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    centre = median(resid)
    scale = max(1.4826 * median(abs(e - centre) for e in resid), SCALE_FLOOR)
    limit = max(Z_THRESHOLD * scale, MIN_POINTS)
    flagged = []
    for r, x, e in zip(rows, xs, resid):
        if abs(e - centre) > limit:
            flagged.append({**r, "expected": intercept + slope * x + centre, "residual": e - centre})
    return flagged

"""Conflicts between kinds of evidence. The job is to surface a disagreement, never to resolve it."""
from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean
from typing import Any

from app.mcp_server.analysis.outliers import kind_class

MIN_SIDE_RECORDS = 6
MIN_SHARED_TERMS = 4
MIN_GAP = 20.0          # points between quiz and coursework averages
MIN_CONSISTENCY = 0.7   # share of shared terms where the gap points the same way (and is >= 10)

# Trait/ability labels. Teacher notes containing these describe a person, not observed work.
LABEL_LEXICON = [
    r"lazy", r"slow learner", r"not (an )?academic", r"weak student", r"dull", r"stupid",
    r"hopeless", r"troublemaker", r"low ability", r"gifted", r"genius", r"bright child",
]
_LABEL_RE = re.compile(r"\b(" + "|".join(LABEL_LEXICON) + r")\b", re.IGNORECASE)


def has_label_language(text: str) -> bool:
    return bool(_LABEL_RE.search(text or ""))


def assessment_type_gap(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """rows: one skill, outliers removed, each with 'ord', 'pct', 'kind'. Returns gap info or None."""
    quiz = [r for r in rows if kind_class(r["kind"]) == "quiz"]
    work = [r for r in rows if kind_class(r["kind"]) == "coursework"]
    if len(quiz) < MIN_SIDE_RECORDS or len(work) < MIN_SIDE_RECORDS:
        return None
    qb, wb = defaultdict(list), defaultdict(list)
    for r in quiz:
        qb[r["ord"]].append(r["pct"])
    for r in work:
        wb[r["ord"]].append(r["pct"])
    shared = sorted(set(qb) & set(wb))
    if len(shared) < MIN_SHARED_TERMS:
        return None
    gap = mean(r["pct"] for r in work) - mean(r["pct"] for r in quiz)
    if abs(gap) < MIN_GAP:
        return None
    diffs = [mean(wb[o]) - mean(qb[o]) for o in shared]
    same = sum(1 for d in diffs if d * gap > 0 and abs(d) >= 10)
    if same / len(shared) < MIN_CONSISTENCY:
        return None
    return {
        "quiz_mean": mean(r["pct"] for r in quiz),
        "coursework_mean": mean(r["pct"] for r in work),
        "gap": gap,
        "terms_consistent": same,
        "terms_shared": len(shared),
        "n_quiz": len(quiz),
        "n_coursework": len(work),
    }

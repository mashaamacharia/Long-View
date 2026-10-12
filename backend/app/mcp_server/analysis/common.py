"""Shared helpers: term arithmetic, score normalisation, de-duplication. Pure functions, no DB, no LLM."""
from __future__ import annotations

import re
from typing import Any

_TERM_RE = re.compile(r"^(\d{4})-T([1-3])$")


def term_ord(term: str) -> int:
    """'2025-T2' -> a sortable integer. Consecutive terms differ by 1, so gaps are measurable."""
    m = _TERM_RE.match(term)
    if not m:
        raise ValueError(f"bad term label: {term!r}")
    return int(m.group(1)) * 3 + int(m.group(2)) - 1


def term_label(o: int) -> str:
    return f"{o // 3}-T{o % 3 + 1}"


def pct(rec: dict[str, Any]) -> float | None:
    """Normalise a score to a percentage so quizzes out of 10 and projects out of 100 are comparable."""
    score, mx = rec.get("score"), rec.get("max_score")
    if score is None or not mx:
        return None
    return 100.0 * float(score) / float(mx)


def dedupe(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop rows that repeat the same assessment (e.g. imported twice from different sources)."""
    seen: set[tuple] = set()
    kept, dropped = [], []
    for r in records:
        key = (r["term"], r["kind"], r["subject"], r.get("skill"), r.get("title"), r.get("score"), r.get("max_score"))
        if key in seen:
            dropped.append(r)
        else:
            seen.add(key)
            kept.append(r)
    return kept, dropped


def missing_terms(ords: list[int]) -> list[str]:
    """Terms inside the observed span that have no data (never extrapolated beyond the span)."""
    if not ords:
        return []
    have = set(ords)
    return [term_label(o) for o in range(min(ords), max(ords) + 1) if o not in have]


def humanise(skill: str | None) -> str:
    return (skill or "overall").replace("_", " ")

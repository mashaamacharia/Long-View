"""Deterministic decisions the agent never leaves to the model. Pure functions."""
from __future__ import annotations

import posixpath
import re
from typing import Any

FLAGGABLE_KINDS = {"strength", "decline", "conflict"}   # things a teacher can approve into a profile
MAX_DOCS = 3
_ALIASES = {"maths": "mathematics", "math": "mathematics"}


def summarise_timeline(tl: dict[str, Any]) -> dict[str, Any]:
    recs = tl.get("records", [])
    subjects = sorted({r["subject"] for r in recs if r["subject"] != "All"})
    terms = sorted({r["term"] for r in recs})
    return {
        "subjects": subjects,
        "skills": {s: sorted({r["skill"] for r in recs if r["subject"] == s and r["skill"]}) for s in subjects},
        "first_term": terms[0] if terms else None, "last_term": terms[-1] if terms else None,
        "n_terms": len(terms), "n_records": len(recs), "n_observations": len(tl.get("observations", [])),
    }


def pick_subject(request: str, subjects: list[str]) -> str | None:
    """A subject focus only if the request names exactly one; otherwise analyse everything."""
    text = (request or "").lower()
    hits = {s for s in subjects if re.search(rf"\b{re.escape(s.lower())}\b", text)}
    for alias, canonical in _ALIASES.items():
        match = next((s for s in subjects if s.lower() == canonical), None)
        if match and re.search(rf"\b{alias}\b", text):
            hits.add(match)
    return next(iter(hits)) if len(hits) == 1 else None


def reportable(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in patterns if p["kind"] != "insufficient"]


def select_candidates(patterns: list[dict[str, Any]]) -> list[str]:
    """Patterns worth a teacher's approval: an approvable kind, enough evidence, not already decided."""
    return [p["pattern_id"] for p in patterns
            if p["kind"] in FLAGGABLE_KINDS and p["evidence_strength"] in ("medium", "high") and p["status"] == "proposed"]


def required_actions(patterns: list[dict[str, Any]], gathered: dict[str, Any], docs_dir: str,
                     has_external: bool) -> list[dict[str, Any]]:
    """The minimum evidence coverage, whatever the model does. Recomputed after every step."""
    needs: list[dict[str, Any]] = []
    rel = reportable(patterns)
    for p in rel:
        if p["pattern_id"] not in gathered.get("evidence", {}):
            needs.append({"tool": "get_evidence", "args": {"pattern_id": p["pattern_id"]}})
    if rel and has_external:
        if not gathered.get("docs_listed"):
            needs.append({"tool": "list_directory", "args": {"path": docs_dir}})
        else:
            for f in gathered.get("doc_files", [])[:MAX_DOCS]:
                path = posixpath.join(docs_dir, f)
                if path not in gathered.get("docs", {}) and path not in gathered.get("docs_failed", []):
                    needs.append({"tool": "read_text_file", "args": {"path": path}})
    return needs


def review_reason(p: dict[str, Any]) -> str:
    return f"{p['statement']} Evidence strength: {p['evidence_strength']} ({p['n_terms']} terms)."[:600]


def describe_need(n: dict[str, Any]) -> str:
    args = ", ".join(f'{k}="{v}"' for k, v in n["args"].items())
    return f"{n['tool']}({args})"

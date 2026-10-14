"""Shrink tool output to what a small model (and the final summary) actually needs. Pure functions."""
from __future__ import annotations

import json
import re
from typing import Any


def _trim(s: str | None, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def compact_evidence(ev: dict[str, Any]) -> dict[str, Any]:
    recs = ev["records"]["items"]
    keep = recs if len(recs) <= 6 else recs[:4] + recs[-2:]
    out = {
        "pattern_id": ev["pattern"]["pattern_id"],
        "records_total": ev["records"]["total"],
        "records": [{"record_id": r["record_id"], "term": r["term"], "kind": r["kind"], "pct": r["pct"]} for r in keep],
        "observations": [{"observation_id": o["observation_id"], "term": o["term"], "teacher_id": o["teacher_id"],
                          "sentiment": o["sentiment"], "text": _trim(o["text"], 160),
                          "characterising_language": o["characterising_language"]}
                         for o in ev["observations"]["items"][:6]],
    }
    if ev.get("attendance"):
        out["attendance"] = ev["attendance"]["items"]
    if ev.get("term_means"):
        out["term_means"] = ev["term_means"]
    return out


def parse_listing(text: str) -> list[str]:
    """Filesystem server listing -> file names ('[FILE] name' lines), documents only."""
    names = [m.group(1).strip() for m in re.finditer(r"^\[FILE\]\s+(.+)$", text or "", re.MULTILINE)]
    return sorted(n for n in names if n.lower().endswith((".md", ".txt")))


def doc_excerpt(text: str, path: str, limit: int = 700) -> dict[str, Any]:
    meta: dict[str, str] = {}
    body = text or ""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", body, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return {"path": path, "term": meta.get("term"), "title": meta.get("title"), "excerpt": _trim(body, limit)}


def for_llm(res: dict[str, Any], limit: int = 1800) -> str:
    s = json.dumps(res, separators=(",", ":"), default=str)
    return s if len(s) <= limit else s[: limit - 1] + "…"

"""Teacher-facing summary: the model writes prose from a FACT SHEET, a verifier checks it, and a
deterministic template is the fallback. Pure functions, no I/O.

The verifier is what makes it safe to let a 4B model write: unknown citations, label or cause
language, numbers that are not in the sheet, and term labels that are not in the sheet all fail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.mcp_server.analysis.conflicts import has_label_language

SYSTEM_PROMPT = (
    "You write a short summary for a teacher from a FACT SHEET.\n"
    "Rules:\n"
    "1. Use only facts in the sheet. Do no arithmetic and add no numbers that are not in the sheet.\n"
    "2. Cite every finding with its pattern id in square brackets, like [PAT-1A2B3C4D], and cite supporting "
    "evidence ids like [R12] [O3] [D1].\n"
    "3. Describe measured change and evidence only. Never name a cause, a diagnosis, a trait or a label for the "
    "learner. Avoid the words 'because' and 'due to'; state conditions as plain facts.\n"
    "4. If the sheet says insufficient data or no pattern, say so plainly.\n"
    "5. Say what is waiting for the teacher and what was written to the profile, exactly as the sheet says.\n"
    "6. Under 180 words. Plain sentences, no headings, no lists."
)

_CAUSE = re.compile(r"\b(because|due to|caused?|causing|as a result of|diagnos\w*|anxiety|dyslex\w*|adhd|autis\w*|"
                    r"disorder|disability|lazy|struggl\w*)\b", re.IGNORECASE)
_CITE = re.compile(r"\[([A-Za-z0-9:_.\-]+)\]")
_TERM = re.compile(r"\b\d{4}-T[1-3]\b")
_ID = re.compile(r"\b(?:PAT-[0-9A-F]+|[ROD]\d+)\b")
_NUM = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Facts:
    text: str
    allowed_ids: set[str] = field(default_factory=set)
    pattern_ids: list[str] = field(default_factory=list)


def _skill(p: dict[str, Any]) -> str:
    return f"{p.get('subject') or 'all subjects'} {(p.get('skill') or '').replace('_', ' ')}".strip()


def _outcome(state: dict[str, Any], pid: str) -> str | None:
    """Where a pattern stands with the teacher. The current round's review wins over earlier decisions."""
    decisions = state.get("decisions", [])

    def describe(d: dict[str, Any]) -> str:
        applied = any(a.get("pattern_id") == pid and a.get("ok") and a.get("approval_id") == d.get("approval_id")
                      for a in state.get("applied", []))
        return f"teacher {d['decision'].replace('_', ' ')}" + ("; written to the profile" if applied else "; nothing written to the profile")

    current = next((r for r in state.get("reviews", []) if r.get("pattern_id") == pid), None)
    if current is not None:
        d = next((d for d in decisions if d.get("review_id") == current["review_id"]), None)
        return describe(d) if d else "sent to the teacher; waiting for their decision; nothing written to the profile"
    past = [d for d in decisions if d.get("pattern_id") == pid]
    return describe(past[-1]) if past else None


def build_facts(state: dict[str, Any]) -> Facts:
    ids: set[str] = set()
    pids: list[str] = []
    L: list[str] = []
    dq = state.get("data_quality", {})
    L.append(f"LEARNER: {state.get('learner_name', '')} ({state['learner_id']})")
    L.append(f"TEACHER REQUEST: {state.get('request', '')}")
    L.append(f"SUBJECT FOCUS: {state.get('subject') or 'all subjects'}")
    tl = state.get("timeline", {})
    missing = dq.get("terms_missing_within_span") or []
    L.append(f"DATA: {tl.get('n_records', dq.get('records_analysed', 0))} records over {tl.get('n_terms', 0)} terms "
             f"({tl.get('first_term')} to {tl.get('last_term')}); duplicates removed: {dq.get('duplicates_removed', 0)}; "
             f"blank scores: {dq.get('blank_scores', 0)}; terms with no data inside the span: "
             f"{', '.join(missing) if missing else 'none'}.")
    late = (dq.get("late_submissions") or {})
    if late.get("rate") is not None and late.get("coursework_records"):
        L.append(f"LATE SUBMISSIONS: {late['late']} of {late['coursework_records']} assignments and projects.")

    evidence = state.get("gathered", {}).get("evidence", {})
    for p in state.get("patterns", []):
        pid = p["pattern_id"]
        ids.add(pid)
        pids.append(pid)
        L.append(f"[{pid}] kind={p['kind']} | {_skill(p)} | evidence={p['evidence_strength']} | terms={p['n_terms']}")
        L.append(f"  STATEMENT: {p['statement']}")
        if p.get("caveats"):
            L.append(f"  CAVEATS: {' '.join(p['caveats'])}")
        ev = evidence.get(pid)
        if ev and "error" in ev:
            L.append(f"  NOTE: the supporting records could not be retrieved ({ev['error']}).")
        if ev and "records" in ev:
            recs = []
            for r in ev["records"]:
                ids.add(f"R{r['record_id']}")
                recs.append(f"R{r['record_id']} ({r['term']} {r['kind']} {r['pct']:.0f}%)" if r.get("pct") is not None
                            else f"R{r['record_id']} ({r['term']} {r['kind']})")
            L.append(f"  RECORDS ({ev['records_total']} in total, sample): {', '.join(recs)}")
            obs = []
            for o in ev.get("observations", []):
                ids.add(f"O{o['observation_id']}")
                obs.append(f"O{o['observation_id']} ({o['term']}, {o['sentiment']}, {o['teacher_id']}): \"{o['text']}\"")
            if obs:
                L.append("  OBSERVATIONS: " + " | ".join(obs))
        out = _outcome(state, pid)
        if out:
            L.append(f"  REVIEW: {out}")

    for i, (path, d) in enumerate(sorted(state.get("gathered", {}).get("docs", {}).items()), start=1):
        ids.add(f"D{i}")
        L.append(f"[D{i}] DOCUMENT {d.get('title') or path} ({d.get('term')}): {d['excerpt']}")

    checked = state.get("checked", [])
    n_flat = sum(1 for c in checked if c["result"] == "no_significant_trend")
    if checked:
        L.append(f"SKILLS CHECKED: {len(checked)}; WITH NO SIGNIFICANT TREND: {n_flat}.")
    quiet = [c for c in checked if c["result"] in ("no_significant_trend", "insufficient")][:8]
    for c in quiet:
        L.append(f"CHECKED, NO PATTERN: {c['subject']} {(c['skill'] or '').replace('_', ' ')}, {c['n_terms']} terms, "
                 f"{c['n_records']} records: {c['result'].replace('_', ' ')}.")
    if not state.get("patterns") and not state.get("checked"):
        L.append("NOTE: there were no scored records to analyse.")
    return Facts("\n".join(L), ids, pids)


def _normalised_numbers(text: str) -> set[str]:
    text = _CITE.sub(" ", text)
    text = _TERM.sub(" ", text)
    text = _ID.sub(" ", text)
    return set(_NUM.findall(text))


def verify(summary: str, facts: Facts) -> list[str]:
    """Return a list of violations (empty = safe to show)."""
    bad: list[str] = []
    text = (summary or "").strip()
    if not text:
        return ["the summary is empty"]
    if len(text.split()) > 260:
        bad.append("the summary is too long (limit about 180 words)")
    cited = set(_CITE.findall(text))
    unknown = sorted(c for c in cited if c not in facts.allowed_ids)
    if unknown:
        bad.append(f"it cites ids that are not in the sheet: {', '.join(unknown)}")
    missing = [p for p in facts.pattern_ids if p not in cited]
    if missing:
        bad.append(f"it does not cite every finding by pattern id; missing: {', '.join(missing)}")
    if has_label_language(text):
        bad.append("it uses a trait or ability label for the learner")
    m = _CAUSE.search(text)
    if m:
        bad.append(f"it uses causal or diagnostic wording ('{m.group(0)}'); state measured facts only")
    extra_nums = sorted(_normalised_numbers(text) - _normalised_numbers(facts.text), key=float)
    if extra_nums:
        bad.append(f"it contains numbers that are not in the sheet: {', '.join(extra_nums)}")
    extra_terms = sorted(set(_TERM.findall(text)) - set(_TERM.findall(facts.text)))
    if extra_terms:
        bad.append(f"it mentions terms that are not in the sheet: {', '.join(extra_terms)}")
    return bad


def retry_message(violations: list[str]) -> str:
    return "Your summary was rejected for these reasons:\n- " + "\n- ".join(violations) + "\nRewrite it, fixing every point."


def template_summary(state: dict[str, Any], facts: Facts) -> str:
    """Deterministic, always verifier-clean. Used when the model is unavailable or fails twice."""
    parts = [f"Summary for {state.get('learner_name', '')} ({state['learner_id']}), based on the records and notes on file."]
    evidence = state.get("gathered", {}).get("evidence", {})
    for p in state.get("patterns", []):
        pid = p["pattern_id"]
        line = f"{p['statement']} [{pid}]"
        if p["evidence_strength"] != "none":
            line += f" Evidence strength: {p['evidence_strength']}."
        ev = evidence.get(pid)
        if ev and "error" in ev:
            line += f" Note: the supporting records could not be retrieved ({ev['error']})."
        if ev and ev.get("records"):
            cites = [f"[R{r['record_id']}]" for r in ev["records"][:3]] + [f"[O{o['observation_id']}]" for o in ev.get("observations", [])[:2]]
            line += " Supporting evidence: " + " ".join(cites) + "."
        if p.get("caveats"):
            line += " Note: " + p["caveats"][0]
        out = _outcome(state, pid)
        if out:
            line += f" Review status: {out}."
        parts.append(line)
    docs = sorted(state.get("gathered", {}).get("docs", {}).items())
    for i, (path, d) in enumerate(docs, start=1):
        parts.append(f"Document [D{i}] ({d.get('title') or path}): {d['excerpt'][:240]}")
    if not state.get("patterns"):
        n_flat = sum(1 for c in state.get("checked", []) if c["result"] == "no_significant_trend")
        if n_flat:
            parts.append(f"No significant trend, strength, decline or conflict was found in {n_flat} skill(s) checked "
                         f"across {state.get('timeline', {}).get('n_terms', 0)} terms; the record looks stable.")
        else:
            parts.append("There were no scored records to analyse.")
    return "\n\n".join(parts)

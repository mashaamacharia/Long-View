"""The LongView agent as a LangGraph state machine.

  fetch_timeline -> detect -> investigate -> triage -> flag -> await_teacher -> apply -> summarise
                                  ^             |  (gaps)             |  (more evidence)    |
                                  +-------------+---------------------+                     v
                                                                                           END

Division of labour:
  * deterministic code decides what must be gathered, which findings go to a teacher, and what is
    written to a profile (only the approved finding's own statement, only after approval)
  * the model chooses its next evidence-gathering tool call inside `investigate` and drafts the
    summary; every call is validated and every draft is verified; failures fall back to code
  * the teacher decides; the graph pauses at `await_teacher` (checkpointed) until they do
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.agent import compact, policy
from app.agent import summary as summ
from app.agent.events import EventLog, set_run
from app.agent.llm import LLM, LLMError
from app.agent.state import AgentState
from app.agent.tools import LLM_EXTERNAL, LLM_OURS, ToolRouter

log = logging.getLogger(__name__)

INVESTIGATE_SYSTEM = (
    "You gather evidence for a teacher's review. You may only call the tools provided. "
    "Do not draw conclusions. Call one tool at a time. When nothing is left under STILL NEEDED, "
    "reply with the single word DONE and call no tool."
)


class ToolFailure(RuntimeError):
    """A tool the run cannot proceed without failed. Never treated as 'no data'."""


@dataclass
class Deps:
    run_id: str
    learner_id: str
    tools: ToolRouter | None
    llm: LLM | None
    events: EventLog
    max_llm_steps: int = 4
    max_rounds: int = 2
    max_loops: int = 2


def _describe(name: str, res: dict[str, Any]) -> str:
    if not res.get("ok", True):
        return f"refused or failed: {str(res.get('error', ''))[:120]}"
    if name == "get_learner_timeline":
        return f"{len(res.get('records', []))} records, {len(res.get('observations', []))} notes"
    if name == "detect_patterns":
        return f"{len(res.get('patterns', []))} pattern(s): {', '.join(p['kind'] for p in res.get('patterns', [])) or 'none'}"
    if name == "get_evidence":
        return f"{res['records']['total']} records, {res['observations']['total']} notes"
    if name == "list_directory":
        return f"{len(compact.parse_listing(res.get('text', '')))} document(s)"
    if name == "read_text_file":
        return f"{len(res.get('text', ''))} characters"
    return str(res.get("message", "ok"))[:120]


def build_graph(d: Deps) -> StateGraph:
    async def act(node: str, name: str, args: dict[str, Any], kind: str = "tool") -> dict[str, Any]:
        t0 = time.monotonic()
        res = await d.tools.call(name, args)
        d.events.add(kind, node, f"{name}: {_describe(name, res)}",
                     {"args": {k: v for k, v in args.items() if k != "summary"}, "ok": res.get("ok", True),
                      "seconds": round(time.monotonic() - t0, 2)})
        return res

    def pattern(state: AgentState, pid: str) -> dict[str, Any] | None:
        return next((p for p in state.get("patterns", []) if p["pattern_id"] == pid), None)

    # ---------- nodes ----------
    async def fetch_timeline(state: AgentState) -> dict[str, Any]:
        res = await act("fetch_timeline", "get_learner_timeline", {})
        if not res.get("ok", True):
            raise ToolFailure(f"Could not read the learner's records: {res.get('error')}")
        tl = policy.summarise_timeline(res)
        subject = policy.pick_subject(state["request"], tl["subjects"])
        d.events.add("node", "fetch_timeline", f"{tl['n_records']} records over {tl['n_terms']} terms; "
                     f"subject focus: {subject or 'all subjects'}")
        return {"timeline": tl, "subject": subject}

    async def detect(state: AgentState) -> dict[str, Any]:
        res = await act("detect", "detect_patterns", {"subject": state["subject"]} if state.get("subject") else {})
        if not res.get("ok", False):
            raise ToolFailure(f"Pattern detection failed: {res.get('error')}")
        return {"patterns": res.get("patterns", []), "checked": res.get("checked", []),
                "data_quality": res.get("data_quality", {})}

    async def investigate(state: AgentState) -> dict[str, Any]:
        patterns = list(state["patterns"])
        gathered = json.loads(json.dumps(state.get("gathered", {})))
        llm_ok, llm_calls, llm_secs = state.get("llm_ok", True), state.get("llm_calls", 0), state.get("llm_seconds", 0.0)
        fallbacks = list(state.get("fallbacks", []))
        followup = state.get("pending_followup")
        subjects = state["timeline"]["subjects"]
        docs_dir = d.tools.learner_docs_dir
        d.events.add("node", "investigate", "Gathering evidence" + (f" (teacher asked: {followup})" if followup else ""))

        def absorb(name: str, args: dict[str, Any], res: dict[str, Any]) -> None:
            nonlocal patterns
            ok = res.get("ok", True)
            if name == "get_evidence":
                pid = args["pattern_id"]
                gathered.setdefault("evidence", {})[pid] = compact.compact_evidence(res) if ok else {"pattern_id": pid, "error": res.get("error")}
            elif name == "list_directory":
                gathered["docs_listed"] = True
                gathered["doc_files"] = compact.parse_listing(res.get("text", "")) if ok else []
            elif name == "read_text_file":
                if ok:
                    gathered.setdefault("docs", {})[args["path"]] = compact.doc_excerpt(res.get("text", ""), args["path"])
                else:
                    gathered.setdefault("docs_failed", []).append(args["path"])
            elif name == "detect_patterns" and ok:
                merged = {p["pattern_id"]: p for p in patterns}
                merged.update({p["pattern_id"]: p for p in res.get("patterns", [])})
                patterns = list(merged.values())

        if state.get("refresh"):   # the teacher asked for more evidence: refresh detection first
            res = await act("investigate", "detect_patterns", {"subject": state["subject"]} if state.get("subject") else {})
            if res.get("ok"):
                patterns = res["patterns"]
                gathered["evidence"] = {}

        def needs() -> list[dict[str, Any]]:
            return policy.required_actions(patterns, gathered, docs_dir, d.tools.has_external)

        allowed = set(LLM_OURS) | (set(LLM_EXTERNAL) if d.tools.has_external else set())
        specs = d.tools.llm_specs(allowed)
        steps, seen, extra_pending = 0, set(), bool(followup)
        messages: list[dict[str, Any]] = []
        if d.llm and llm_ok:
            lines = [f"Teacher request: {state['request']}",
                     f"Learner: {state.get('learner_name', '')}. Subject focus: {state.get('subject') or 'all subjects'}.",
                     "Candidate findings (not conclusions):"]
            for p in patterns:
                lines.append(f"- {p['pattern_id']} [{p['kind']}, {p['subject']}/{p['skill']}, evidence {p['evidence_strength']}]: {p['statement'][:200]}")
            lines.append("STILL NEEDED:")
            lines += [f"- {policy.describe_need(n)}" for n in needs()] or ["- nothing"]
            if followup:
                lines.append(f"The teacher asked: {followup}. You may call one extra tool to address it.")
            messages = [{"role": "system", "content": INVESTIGATE_SYSTEM}, {"role": "user", "content": "\n".join(lines)}]

        while d.llm and llm_ok and steps < d.max_llm_steps and (needs() or extra_pending):
            try:
                resp = await d.llm.chat(messages, tools=specs)
            except LLMError as exc:
                llm_ok = False
                fallbacks.append(f"llm_unavailable: {exc}")
                d.events.add("error", "investigate", "Model unavailable; continuing with deterministic evidence gathering", {"error": str(exc)})
                break
            steps += 1
            llm_calls += 1
            llm_secs += resp.seconds
            extra_pending = False
            d.events.add("llm", "investigate", f"Model chose: {resp.tool_calls[0].name if resp.tool_calls else 'DONE'} ({resp.seconds:.0f}s)",
                         {"content": resp.content[:200], "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in resp.tool_calls]})
            if not resp.tool_calls:
                if needs():
                    fallbacks.append("model stopped with evidence still outstanding")
                break
            call = resp.tool_calls[0]
            cid = call.id or f"call_{steps}"
            messages.append({"role": "assistant", "content": resp.content or "",
                             "tool_calls": [{"id": cid, "name": call.name, "arguments": call.arguments}]})
            clean, problem = d.tools.check_llm_call(call.name, call.arguments, allowed=allowed,
                                                    pattern_ids=[p["pattern_id"] for p in patterns], subjects=subjects)
            if problem:
                fallbacks.append(f"rejected model tool call {call.name}: {problem}")
                d.events.add("rejected", "investigate", f"Rejected {call.name}: {problem}", {"arguments": call.arguments})
                messages.append({"role": "tool", "tool_call_id": cid, "name": call.name, "content": f"Rejected: {problem}"})
                continue
            key = (call.name, json.dumps(clean, sort_keys=True))
            if key in seen:
                messages.append({"role": "tool", "tool_call_id": cid, "name": call.name, "content": "Already retrieved."})
                continue
            seen.add(key)
            res = await act("investigate", call.name, clean)
            absorb(call.name, clean, res)
            left = needs()
            hint = ("\nSTILL NEEDED: " + "; ".join(policy.describe_need(n) for n in left)) if left else "\nNothing is left to retrieve. Reply DONE."
            messages.append({"role": "tool", "tool_call_id": cid, "name": call.name, "content": compact.for_llm(res) + hint})

        guard = 0   # safety net: the minimum coverage always happens, model or not
        while guard < 12 and (todo := needs()):
            guard += 1
            action = todo[0]
            if d.llm and llm_ok:
                fallbacks.append(f"forced {policy.describe_need(action)}")
            res = await act("investigate", action["tool"], action["args"], kind="forced")
            absorb(action["tool"], action["args"], res)
        return {"patterns": patterns, "gathered": gathered, "llm_ok": llm_ok, "llm_calls": llm_calls, "llm_seconds": llm_secs,
                "fallbacks": fallbacks, "loops": state.get("loops", 0) + 1, "refresh": False, "pending_followup": None}

    async def triage(state: AgentState) -> dict[str, Any]:
        cands = policy.select_candidates(state["patterns"])
        d.events.add("node", "triage", f"{len(cands)} finding(s) for the teacher; "
                     f"{len(policy.reportable(state['patterns'])) - len(cands)} reported without approval")
        return {"candidates": cands}

    async def flag(state: AgentState) -> dict[str, Any]:
        reviews = []
        for pid in state["candidates"]:
            p = pattern(state, pid)
            res = await act("flag", "flag_for_teacher_review", {"pattern_id": pid, "reason": policy.review_reason(p)})
            if res.get("ok"):
                reviews.append({"review_id": res["review_id"], "pattern_id": pid})
        if reviews:
            set_run(d.run_id, state="waiting_for_teacher")
            d.events.add("interrupt", "flag", f"Waiting for the teacher: {len(reviews)} finding(s) need a decision",
                         {"review_ids": [r["review_id"] for r in reviews]})
        return {"reviews": reviews, "rounds": state.get("rounds", 0) + (1 if reviews else 0)}

    def await_teacher(state: AgentState) -> dict[str, Any]:
        payload = interrupt({"review_ids": [r["review_id"] for r in state["reviews"]]})
        d.events.add("resume", "await_teacher", "The teacher has decided; resuming",
                     {"decisions": [{"review_id": x["review_id"], "decision": x["decision"]} for x in payload]})
        return {"pending_decisions": payload}

    async def apply(state: AgentState) -> dict[str, Any]:
        decisions = list(state.get("decisions", [])) + list(state.get("pending_decisions", []))
        applied, followups = list(state.get("applied", [])), list(state.get("followups", []))
        asked = []
        for dec in state.get("pending_decisions", []):
            p = pattern(state, dec["pattern_id"])
            if dec["decision"] == "approved" and p:
                res = await act("apply", "update_learner_profile",
                                {"pattern_id": dec["pattern_id"], "summary": p["statement"], "approval_id": dec["approval_id"]})
                applied.append({"pattern_id": dec["pattern_id"], "approval_id": dec["approval_id"], "ok": bool(res.get("ok")),
                                "change_id": res.get("change_id"), "error": res.get("error")})
            elif dec["decision"] == "more_evidence":
                asked.append((dec.get("comment") or "more evidence requested").strip())
        text = "; ".join(asked) or None
        if text:
            followups.append(text)
        return {"decisions": decisions, "applied": applied, "followups": followups, "pending_followup": text,
                "refresh": bool(text), "pending_decisions": []}

    async def summarise(state: AgentState) -> dict[str, Any]:
        facts = summ.build_facts(state)
        llm_ok, llm_calls, llm_secs = state.get("llm_ok", True), state.get("llm_calls", 0), state.get("llm_seconds", 0.0)
        fallbacks, text, source, violations, retried = list(state.get("fallbacks", [])), None, "template", [], False
        repairs: list[tuple[str, str]] = []
        d.events.add("node", "summarise", "Writing the summary")
        if d.llm and llm_ok:
            messages = [{"role": "system", "content": summ.SYSTEM_PROMPT}, {"role": "user", "content": facts.text}]
            for attempt in (1, 2):
                try:
                    resp = await d.llm.chat(messages, max_tokens=500)
                except LLMError as exc:
                    llm_ok = False
                    fallbacks.append(f"llm_unavailable: {exc}")
                    d.events.add("error", "summarise", "Model unavailable; using the template summary", {"error": str(exc)})
                    break
                llm_calls += 1
                llm_secs += resp.seconds
                draft, fixed = summ.repair_citations(resp.content, facts)
                repairs += fixed
                violations = summ.verify(draft, facts)
                d.events.add("llm", "summarise", f"Draft {attempt} written ({resp.seconds:.0f}s)",
                             {"violations": violations, "repaired_citations": fixed})
                if not violations:
                    text, source = draft.strip(), "llm"
                    break
                retried = True
                d.events.add("rejected", "summarise", "Draft rejected by the verifier", {"violations": violations})
                messages += [{"role": "assistant", "content": resp.content}, {"role": "user", "content": summ.retry_message(violations, facts)}]
            if text is None and llm_ok:
                fallbacks.append("summary draft failed verification twice; used the template")
        if text is None:
            text = summ.template_summary(state, facts)
        findings = [{"pattern_id": p["pattern_id"], "kind": p["kind"], "subtype": p.get("subtype"), "subject": p["subject"],
                     "skill": p["skill"], "evidence_strength": p["evidence_strength"], "statement": p["statement"],
                     "outcome": summ._outcome(state, p["pattern_id"])} for p in state.get("patterns", [])]
        result = {
            "summary": text, "summary_source": source,
            "verification": {"violations": violations if source != "llm" else [], "retried": retried,
                             "repaired_citations": [{"wrote": a, "fixed_to": b} for a, b in repairs]},
            "findings": findings, "documents_consulted": sorted(state.get("gathered", {}).get("docs", {})),
            "profile_changes": [a for a in state.get("applied", []) if a.get("ok")],
            "fallbacks": fallbacks, "checked": state.get("checked", []), "data_quality": state.get("data_quality", {}),
            "rounds": state.get("rounds", 0), "evidence_passes": state.get("loops", 0),
            "llm": {"provider": getattr(d.llm, "provider", None), "model": getattr(d.llm, "model", None),
                    "calls": llm_calls, "seconds": round(llm_secs, 1), "available": llm_ok},
        }
        set_run(d.run_id, state="completed", result=result)
        d.events.add("final", "summarise", f"Done ({source} summary, {len(findings)} finding(s))")
        return {"summary": text, "result": result, "llm_ok": llm_ok, "llm_calls": llm_calls, "llm_seconds": llm_secs, "fallbacks": fallbacks}

    # ---------- routing ----------
    def after_timeline(state: AgentState) -> str:
        return "detect" if state["timeline"]["n_records"] > 0 else "summarise"

    def after_detect(state: AgentState) -> str:
        return "investigate" if policy.reportable(state["patterns"]) else "summarise"

    def after_triage(state: AgentState) -> str:
        gaps = policy.required_actions(state["patterns"], state.get("gathered", {}), d.tools.learner_docs_dir if d.tools else "", bool(d.tools and d.tools.has_external))
        if gaps and state.get("loops", 0) < d.max_loops:
            return "investigate"
        return "flag" if state["candidates"] else "summarise"

    def after_flag(state: AgentState) -> str:
        return "await_teacher" if state["reviews"] else "summarise"

    def after_apply(state: AgentState) -> str:
        return "investigate" if state.get("pending_followup") and state.get("rounds", 0) < d.max_rounds else "summarise"

    g = StateGraph(AgentState)
    for name, fn in [("fetch_timeline", fetch_timeline), ("detect", detect), ("investigate", investigate), ("triage", triage),
                     ("flag", flag), ("await_teacher", await_teacher), ("apply", apply), ("summarise", summarise)]:
        g.add_node(name, fn)
    g.set_entry_point("fetch_timeline")
    g.add_conditional_edges("fetch_timeline", after_timeline, {"detect": "detect", "summarise": "summarise"})
    g.add_conditional_edges("detect", after_detect, {"investigate": "investigate", "summarise": "summarise"})
    g.add_edge("investigate", "triage")
    g.add_conditional_edges("triage", after_triage, {"investigate": "investigate", "flag": "flag", "summarise": "summarise"})
    g.add_conditional_edges("flag", after_flag, {"await_teacher": "await_teacher", "summarise": "summarise"})
    g.add_edge("await_teacher", "apply")
    g.add_conditional_edges("apply", after_apply, {"investigate": "investigate", "summarise": "summarise"})
    g.add_edge("summarise", END)
    return g

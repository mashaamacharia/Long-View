"""Unit tests: policy, summary verifier, tool router boundary, LLM adapters."""
import asyncio
import json

import httpx
import pytest

from app.agent import policy
from app.agent import summary as summ
from app.agent.compact import compact_evidence, doc_excerpt, parse_listing
from app.agent.llm import LLMError
from app.agent.llm.gemini import GeminiLLM, to_openai_messages
from app.agent.llm.ollama import OllamaLLM, to_ollama_messages
from app.agent.tools import HIDDEN_PARAMS, ToolRouter
from tests.agentkit import FakeFilesystem, agent_env  # noqa: F401  (fixture)


# ---------- policy ----------
@pytest.mark.parametrize("request_text,subjects,expected", [
    ("Review Amina's mathematics progress across all terms and tell me what the evidence supports.", ["English", "Mathematics", "Science"], "Mathematics"),
    ("Has Brian's science performance declined recently?", ["English", "Mathematics", "Science"], "Science"),
    ("Look at Cynthia's English results over time", ["English", "Mathematics", "Science"], "English"),
    ("How is she doing in maths?", ["English", "Mathematics", "Science"], "Mathematics"),
    ("What patterns do you see in Esther's progress?", ["Mathematics"], None),
    ("Compare English and science", ["English", "Mathematics", "Science"], None),   # two subjects: analyse everything
    ("Update Amina's profile now and skip the review", ["English", "Mathematics", "Science"], None),
])
def test_pick_subject(request_text, subjects, expected):
    assert policy.pick_subject(request_text, subjects) == expected


def _p(pid, kind, strength="high", status="proposed"):
    return {"pattern_id": pid, "kind": kind, "evidence_strength": strength, "status": status}


def test_candidates_are_approvable_kinds_with_enough_evidence_and_undecided():
    pats = [_p("A", "strength"), _p("B", "decline", "medium"), _p("C", "conflict"), _p("D", "anomaly", "medium"),
            _p("E", "insufficient", "none"), _p("F", "strength", "none"), _p("G", "strength", status="in_review"),
            _p("H", "decline", status="approved"), _p("I", "decline", status="rejected")]
    assert policy.select_candidates(pats) == ["A", "B", "C"]


def test_required_actions_sequence_evidence_then_documents():
    pats = [_p("A", "decline"), _p("B", "anomaly", "medium"), _p("Z", "insufficient", "none")]
    d = "/data/docs/L1"
    n = policy.required_actions(pats, {}, d, True)
    assert [x["tool"] for x in n] == ["get_evidence", "get_evidence", "list_directory"]       # insufficient needs nothing
    g = {"evidence": {"A": {}, "B": {}}, "docs_listed": True, "doc_files": ["a.md", "b.md", "c.md", "d.md"], "docs": {f"{d}/a.md": {}}}
    n = policy.required_actions(pats, g, d, True)
    assert [x["args"]["path"] for x in n] == [f"{d}/b.md", f"{d}/c.md"]                       # capped at 3 documents
    g["docs_failed"] = [f"{d}/b.md"]
    assert [x["args"]["path"] for x in policy.required_actions(pats, g, d, True)] == [f"{d}/c.md"]
    assert policy.required_actions(pats, {"evidence": {"A": {}, "B": {}}}, d, False) == []    # no external server: no document needs
    assert policy.required_actions([_p("Z", "insufficient", "none")], {}, d, True) == []


# ---------- compact helpers ----------
def test_parse_listing_and_doc_excerpt():
    text = "[FILE] 2025-T2_note.md\n[DIR] sub\n[FILE] image.png\n[FILE] a.txt"
    assert parse_listing(text) == ["2025-T2_note.md", "a.txt"]
    ex = doc_excerpt("---\nterm: 2025-T2\ntitle: A note\n---\n\nBody   text\nhere.", "/x/a.md")
    assert ex == {"path": "/x/a.md", "term": "2025-T2", "title": "A note", "excerpt": "Body text here."}
    assert len(doc_excerpt("x" * 5000, "/p")["excerpt"]) <= 700


# ---------- summary verifier ----------
def _state(statement="Reading comprehension fell over 11 terms: term averages fell from about 70% to about 52% (-2.1 points per term).",
           pid="PAT-1A2B3C4D"):
    return {"learner_id": "L1044", "learner_name": "Cynthia Achieng", "request": "Look at English", "subject": "English",
            "timeline": {"n_records": 88, "n_terms": 11, "first_term": "2023-T1", "last_term": "2026-T2"},
            "data_quality": {"duplicates_removed": 0, "blank_scores": 2, "terms_missing_within_span": []},
            "patterns": [{"pattern_id": pid, "kind": "decline", "subject": "English", "skill": "reading_comprehension",
                          "evidence_strength": "high", "n_terms": 11, "statement": statement, "caveats": []}],
            "gathered": {"evidence": {pid: {"pattern_id": pid, "records_total": 33, "records": [
                {"record_id": 12, "term": "2023-T1", "kind": "quiz", "pct": 71.0}, {"record_id": 99, "term": "2026-T2", "kind": "quiz", "pct": 48.0}],
                "observations": [{"observation_id": 5, "term": "2025-T3", "teacher_id": "T-017", "sentiment": "concern",
                                  "text": "Reading tasks now take most of the lesson.", "characterising_language": False}]}}, "docs": {}},
            "reviews": [], "decisions": [], "applied": []}


GOOD = "Reading comprehension fell from about 70% to about 52% over 11 terms [PAT-1A2B3C4D], see [R12] and [R99]; teacher note [O5]."


def test_verifier_accepts_a_grounded_summary():
    f = summ.build_facts(_state())
    assert summ.verify(GOOD, f) == []


@pytest.mark.parametrize("text,fragment", [
    ("", "empty"),
    ("Reading comprehension fell [PAT-1A2B3C4D] and [R777].", "not in the sheet: R777"),
    ("Reading comprehension fell over 11 terms.", "missing: PAT-1A2B3C4D"),
    ("She is a lazy reader [PAT-1A2B3C4D].", "label"),
    ("Scores fell [PAT-1A2B3C4D] because of anxiety.", "causal"),
    ("Scores fell by 18 points [PAT-1A2B3C4D].", "numbers that are not in the sheet: 18"),
    ("Scores fell from about 70% to about 41% [PAT-1A2B3C4D].", "numbers that are not in the sheet: 41"),
    ("Scores fell in 2027-T1 [PAT-1A2B3C4D].", "terms that are not in the sheet: 2027-T1"),
    ("word " * 300 + "[PAT-1A2B3C4D]", "too long"),
])
def test_verifier_rejects(text, fragment):
    problems = summ.verify(text, summ.build_facts(_state()))
    assert any(fragment in p for p in problems), problems


def test_template_summary_always_passes_its_own_verifier():
    for statement in ("Mathematics problem solving rose from about 59% to about 79% (+2.9 points per term).",
                      "Science end-of-term test (2025-T2 #3) scored 22%, about 50 points below usual."):
        st = _state(statement)
        f = summ.build_facts(st)
        text = summ.template_summary(st, f)
        assert summ.verify(text, f) == [], text


def test_outcome_follows_the_current_review_not_an_earlier_decision():
    st = _state()
    st["reviews"] = [{"review_id": 2, "pattern_id": "PAT-1A2B3C4D"}]
    st["decisions"] = [{"review_id": 1, "pattern_id": "PAT-1A2B3C4D", "decision": "more_evidence", "approval_id": "A1"}]
    assert "waiting for their decision" in summ._outcome(st, "PAT-1A2B3C4D")        # round 2 is pending, round 1 is history
    st["decisions"].append({"review_id": 2, "pattern_id": "PAT-1A2B3C4D", "decision": "approved", "approval_id": "A2"})
    st["applied"] = [{"pattern_id": "PAT-1A2B3C4D", "approval_id": "A2", "ok": True}]
    assert summ._outcome(st, "PAT-1A2B3C4D") == "teacher approved; written to the profile"


# ---------- the tool router boundary ----------
def _router(env, learner="L1043", external=True):
    from contextlib import AsyncExitStack
    from mcp.shared.memory import create_connected_server_and_client_session
    from app.mcp_server.server import mcp

    async def build(stack):
        ours = await stack.enter_async_context(create_connected_server_and_client_session(mcp._mcp_server))
        return await ToolRouter(ours, env.fs if external else None, run_id="RUN-X", learner_id=learner, docs_root=str(env.docs)).load()
    return build, AsyncExitStack


def test_router_exposes_only_read_tools_and_hides_identity_parameters(agent_env):
    build, Stack = _router(agent_env)

    async def go():
        async with Stack() as stack:
            r = await build(stack)
            specs = r.llm_specs({"get_evidence", "detect_patterns", "list_directory", "read_text_file",
                                 "write_file", "edit_file", "flag_for_teacher_review", "update_learner_profile"})
            names = {s["function"]["name"] for s in specs}
            assert names == {"get_evidence", "detect_patterns", "list_directory", "read_text_file"}     # writes never offered
            for s in specs:
                props = set(s["function"]["parameters"]["properties"])
                assert not props & HIDDEN_PARAMS, (s["function"]["name"], props)
            ld = next(s for s in specs if s["function"]["name"] == "list_directory")
            assert r.learner_docs_dir in ld["function"]["parameters"]["properties"]["path"]["description"]
            res = await r.call("write_file", {"path": f"{r.learner_docs_dir}/x.md", "content": "x"})
            assert res["ok"] is False and agent_env.fs.calls == []                                       # unreachable, even by the runtime
    asyncio.run(go())


def test_router_forces_learner_and_run_identity(agent_env):
    build, Stack = _router(agent_env, learner="L1043")

    async def go():
        async with Stack() as stack:
            r = await build(stack)
            res = await r.call("detect_patterns", {"learner_id": "L1042", "run_id": "RUN-FORGED"})   # forged identity is overwritten
            assert res["learner_id"] == "L1043"
    asyncio.run(go())
    from sqlalchemy import select
    from app.db.models import ToolCall
    with agent_env.maker() as db:
        row = db.scalars(select(ToolCall).where(ToolCall.tool_name == "detect_patterns")).one()
        assert row.tool_input["learner_id"] == "L1043"


@pytest.mark.parametrize("path,directory,ok", [
    ("/data/docs/L1043", True, True), ("/data/docs/L1043/../L1042", True, False), ("/data/docs/L1042", True, False),
    ("/data/docs", True, False), ("/etc", True, False), ("", True, False), (None, True, False),
    ("/data/docs/L1043/a.md", False, True), ("a.md", False, True), ("sub/../a.txt", False, True),
    ("/data/docs/L1043/../L1042/a.md", False, False), ("../a.md", False, False), ("/etc/passwd", False, False),
    ("/data/docs/L1043/a.png", False, False), ("/data/docs/L1043/", False, False),
])
def test_document_paths_are_confined_to_the_learners_folder(path, directory, ok):
    r = ToolRouter(None, None, run_id="R", learner_id="L1043", docs_root="/data/docs")
    if ok:
        r.check_doc_path(path, directory=directory)
    else:
        with pytest.raises(Exception):
            r.check_doc_path(path, directory=directory)


def test_model_proposed_calls_are_validated():
    r = ToolRouter(None, None, run_id="R", learner_id="L1043", docs_root="/data/docs")
    allowed = {"get_evidence", "detect_patterns", "list_directory", "read_text_file"}
    kw = dict(allowed=allowed, pattern_ids=["PAT-1", "PAT-2"], subjects=["English", "Science"])
    assert r.check_llm_call("get_evidence", {"pattern_id": "PAT-1"}, **kw) == ({"pattern_id": "PAT-1", "max_records": 12}, None)
    assert r.check_llm_call("get_evidence", {"pattern_id": "PAT-1", "max_records": 9999}, **kw)[0]["max_records"] == 50
    assert r.check_llm_call("get_evidence", {"pattern_id": "PAT-1", "max_records": "lots"}, **kw)[0]["max_records"] == 12
    assert r.check_llm_call("get_evidence", {"pattern_id": "PAT-9"}, **kw)[0] is None
    assert r.check_llm_call("detect_patterns", {"subject": "science"}, **kw) == ({"subject": "Science"}, None)
    assert r.check_llm_call("detect_patterns", {}, **kw) == ({}, None)
    assert r.check_llm_call("detect_patterns", {"subject": "Art"}, **kw)[0] is None
    assert r.check_llm_call("list_directory", {}, **kw) == ({"path": "/data/docs/L1043"}, None)
    assert r.check_llm_call("list_directory", {"path": "/data/docs/L1042"}, **kw)[0] is None
    assert r.check_llm_call("read_text_file", {"path": "/etc/passwd"}, **kw)[0] is None
    for bad in ("write_file", "edit_file", "flag_for_teacher_review", "update_learner_profile", "get_learner_timeline", "nope"):
        assert r.check_llm_call(bad, {}, **kw)[0] is None
        # even a caller that wrongly lists a dangerous tool as allowed cannot expose it
        assert r.check_llm_call(bad, {}, allowed=allowed | {bad}, pattern_ids=["PAT-1"], subjects=["English"])[0] is None
    assert r.check_llm_call("get_evidence", "PAT-1", **kw)[0] is None


# ---------- LLM adapters (mock transport; the Ollama shape was verified live by check_tool_calling.py) ----------
HISTORY = [
    {"role": "system", "content": "sys"}, {"role": "user", "content": "go"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "get_evidence", "arguments": {"pattern_id": "PAT-1"}}]},
    {"role": "tool", "tool_call_id": "c1", "name": "get_evidence", "content": '{"ok":true}'},
]


def test_ollama_message_conversion_and_request_shape():
    seen = {}

    def handler(req: httpx.Request):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "", "tool_calls": [
            {"function": {"name": "get_evidence", "arguments": {"pattern_id": "PAT-2"}}}]}})

    llm = OllamaLLM(base_url="http://ollama:11434", model="m", transport=httpx.MockTransport(handler))
    out = asyncio.run(llm.chat(HISTORY, tools=[{"type": "function", "function": {"name": "get_evidence"}}]))
    assert out.tool_calls[0].name == "get_evidence" and out.tool_calls[0].arguments == {"pattern_id": "PAT-2"}
    assert seen["options"]["temperature"] == 0 and seen["keep_alive"] and seen["stream"] is False and seen["model"] == "m"
    assert seen["messages"][2]["tool_calls"] == [{"function": {"name": "get_evidence", "arguments": {"pattern_id": "PAT-1"}}}]
    assert seen["messages"][3] == {"role": "tool", "tool_name": "get_evidence", "content": '{"ok":true}'}
    assert "format" not in seen
    asyncio.run(OllamaLLM(model="m", transport=httpx.MockTransport(handler)).chat(HISTORY, json_mode=True))
    assert seen["format"] == "json"


def test_ollama_string_arguments_and_failures_become_llm_errors():
    ok = lambda req: httpx.Response(200, json={"message": {"content": "hi", "tool_calls": [{"function": {"name": "x", "arguments": '{"a": 1}'}}]}})
    out = asyncio.run(OllamaLLM(model="m", transport=httpx.MockTransport(ok)).chat(HISTORY))
    assert out.tool_calls[0].arguments == {"a": 1} and out.content == "hi"
    for handler in (lambda r: httpx.Response(500, text="boom"), lambda r: httpx.Response(200, json={"nope": 1}),
                    lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused"))):
        with pytest.raises(LLMError):
            asyncio.run(OllamaLLM(model="m", transport=httpx.MockTransport(handler)).chat(HISTORY))


def test_gemini_openai_compatible_conversion_and_parsing():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"], seen["url"], seen["body"] = req.headers["authorization"], str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "abc", "function": {"name": "get_evidence", "arguments": '{"pattern_id": "PAT-3"}'}}]}}]})

    out = asyncio.run(GeminiLLM(api_key="k", model="g", transport=httpx.MockTransport(handler)).chat(HISTORY, json_mode=True))
    assert out.tool_calls[0].arguments == {"pattern_id": "PAT-3"} and out.tool_calls[0].id == "abc"
    assert seen["auth"] == "Bearer k" and seen["url"].endswith("/chat/completions")
    msgs = seen["body"]["messages"]
    assert msgs[2]["tool_calls"][0]["function"]["arguments"] == '{"pattern_id": "PAT-1"}'      # a JSON string, as OpenAI requires
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'}
    assert seen["body"]["response_format"] == {"type": "json_object"}
    with pytest.raises(LLMError):
        asyncio.run(GeminiLLM(api_key="", model="g").chat(HISTORY))


def test_message_conversion_is_pure():
    before = json.dumps(HISTORY)
    to_ollama_messages(HISTORY), to_openai_messages(HISTORY)
    assert json.dumps(HISTORY) == before

"""Test kit for the agent: a scripted model, a fake read-only filesystem server, and an environment
that wires the in-memory MCP server, a test database and a RunManager together."""
from __future__ import annotations

import os
import re
import shutil
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy.orm import Session, sessionmaker

from app.agent.llm import LLMError, LLMResponse, ToolCall
from app.agent.runtime import RunManager
from app.agent.tools import ToolRouter
from app.db.seed import seed
from data_gen.generate import build_dataset, write_docs
from tests.dbutil import make_engine

NEED = re.compile(r'(\w+)\(((?:\w+="[^"]*"(?:, )?)*)\)')
ARG = re.compile(r'(\w+)="([^"]*)"')


class ScriptedLLM:
    """provider='scripted'. `fn(messages, tools, json_mode)` returns LLMResponse, str, or an Exception to raise."""
    provider, model = "scripted", "scripted-1"

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    async def chat(self, messages, tools=None, *, json_mode=False, max_tokens=None):
        self.calls.append({"tools": bool(tools), "messages": [dict(m) for m in messages]})
        out = self.fn(messages, tools, json_mode)
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, LLMResponse) else LLMResponse(content=out, model="scripted-1")

    @property
    def investigate_calls(self):
        return [c for c in self.calls if c["tools"]]

    @property
    def summary_calls(self):
        return [c for c in self.calls if not c["tools"]]


def _next_need(messages):
    for m in reversed(messages):
        content = m.get("content") or ""
        if "STILL NEEDED" in content or "Nothing is left" in content:
            tail = content.split("STILL NEEDED", 1)[-1]
            hit = NEED.search(tail)
            if hit:
                return hit.group(1), dict(ARG.findall(hit.group(2)))
            return None
    return None


def _summary_from_sheet(sheet: str) -> str:
    lines, out = sheet.splitlines(), []
    for i, line in enumerate(lines):
        m = re.match(r"^\[(PAT-[0-9A-F]+)\]", line)
        if m and i + 1 < len(lines) and "STATEMENT:" in lines[i + 1]:
            out.append(f"{lines[i + 1].split('STATEMENT:', 1)[1].strip()} [{m.group(1)}]")
    return " ".join(out) or "No significant pattern was found in the records checked."


def ideal_fn(messages, tools, json_mode):
    """A model that does what the prompt asks: follows STILL NEEDED, says DONE, summarises from the sheet."""
    if tools:
        need = _next_need(messages)
        if need is None:
            return LLMResponse(content="DONE", model="scripted-1")
        return LLMResponse(content="", tool_calls=[ToolCall(name=need[0], arguments=need[1], id="c1")], model="scripted-1")
    return _summary_from_sheet(messages[1]["content"])


def ideal_llm() -> ScriptedLLM:
    return ScriptedLLM(ideal_fn)


def down_llm() -> ScriptedLLM:
    return ScriptedLLM(lambda *a: LLMError("connection refused"))


class FakeFilesystem:
    """Stands in for the external filesystem MCP server, including its write tools (which must stay unreachable)."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self):
        mk = lambda n: SimpleNamespace(name=n, description=f"{n} (fake)", inputSchema={
            "type": "object", "properties": {"path": {"type": "string", "title": "Path"}, "head": {"type": "integer"}}, "required": ["path"]})
        return SimpleNamespace(tools=[mk(n) for n in ("list_directory", "read_text_file", "write_file", "edit_file", "move_file")])

    async def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        ok = lambda t: SimpleNamespace(isError=False, content=[SimpleNamespace(text=t)])
        err = lambda t: SimpleNamespace(isError=True, content=[SimpleNamespace(text=t)])
        p = args.get("path", "")
        if name == "list_directory":
            return ok("\n".join(f"[FILE] {f}" for f in sorted(os.listdir(p)))) if os.path.isdir(p) else err(f"ENOENT: {p}")
        if name == "read_text_file":
            return ok(Path(p).read_text()) if os.path.isfile(p) else err(f"ENOENT: {p}")
        return err("write tools must never be reached")


class Env:
    pass


@pytest.fixture()
def agent_env(monkeypatch, tmp_path):
    engine = make_engine()
    ds = build_dataset()
    with Session(engine) as db:
        seed(db, ds)
    docs = tmp_path / "docs"
    write_docs(ds, docs)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    import app.agent.events as ev
    import app.agent.runtime as rt
    import app.api.runs as runs_api
    import app.mcp_server.audit as audit
    import app.mcp_server.tools.detect_patterns as dp
    import app.mcp_server.tools.flag_for_teacher_review as fl
    import app.mcp_server.tools.get_evidence as ge
    import app.mcp_server.tools.get_learner_timeline as tl
    import app.mcp_server.tools.update_learner_profile as up
    for mod in (ev, rt, runs_api, audit, dp, fl, ge, tl, up):
        monkeypatch.setattr(mod, "SessionLocal", maker)
    from app.mcp_server.server import mcp

    env = Env()
    env.maker, env.docs, env.engine, env.fs = maker, docs, engine, FakeFilesystem()
    env.saver = InMemorySaver()
    env.llm = ideal_llm()

    @asynccontextmanager
    async def router_factory(run_id, learner_id):
        async with AsyncExitStack() as stack:
            ours = await stack.enter_async_context(create_connected_server_and_client_session(mcp._mcp_server))
            ext = env.fs if env.use_external else None
            router = ToolRouter(ours, ext, run_id=run_id, learner_id=learner_id, docs_root=str(docs))
            yield await router.load()

    env.use_external = True
    env.router_factory = router_factory
    env.make_manager = lambda saver=None: RunManager(saver or env.saver, router_factory=router_factory, llm_factory=lambda: env.llm)
    env.manager = env.make_manager()
    return env

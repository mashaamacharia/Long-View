"""The agent against the REAL external filesystem MCP server (stdio). Skipped if it is not installed:
    npm install -g @modelcontextprotocol/server-filesystem   (the backend Docker image includes it)"""
import asyncio
import os
import shutil
from contextlib import AsyncExitStack, asynccontextmanager

import pytest

from tests.agentkit import agent_env  # noqa: F401
from tests.test_agent_graph import TASKS, events, facts, final_state, go, row

CMD = os.environ.get("DOCS_MCP_COMMAND", "mcp-server-filesystem")
pytestmark = pytest.mark.skipif(shutil.which(CMD) is None, reason=f"{CMD} is not installed")


@pytest.fixture()
def real_fs(agent_env):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.shared.memory import create_connected_server_and_client_session
    from app.agent.tools import ToolRouter
    from app.mcp_server.server import mcp

    @asynccontextmanager
    async def factory(run_id, learner_id):
        async with AsyncExitStack() as stack:
            ours = await stack.enter_async_context(create_connected_server_and_client_session(mcp._mcp_server))
            r, w = await stack.enter_async_context(stdio_client(StdioServerParameters(command=CMD, args=[str(agent_env.docs)])))
            ext = await stack.enter_async_context(ClientSession(r, w))
            await ext.initialize()
            agent_env.ext_session = ext
            yield await ToolRouter(ours, ext, run_id=run_id, learner_id=learner_id, docs_root=str(agent_env.docs)).load()

    agent_env.router_factory = factory
    agent_env.manager = agent_env.make_manager()
    return agent_env


def test_real_server_exposes_write_tools_but_the_agent_can_never_reach_them(real_fs):
    async def main():
        async with real_fs.router_factory("RUN-X", "L1043") as r:
            names = {t.name for t in (await real_fs.ext_session.list_tools()).tools}
            assert {"write_file", "edit_file", "move_file"} <= names                       # the server really offers writes
            assert {s["function"]["name"] for s in r.llm_specs(names | {"get_evidence"})} == {"get_evidence", "list_directory", "read_text_file"}
            target = real_fs.docs / "L1043" / "planted.md"
            res = await r.call("write_file", {"path": str(target), "content": "x"})
            assert res["ok"] is False and not target.exists()
            ok = await r.call("list_directory", {"path": r.learner_docs_dir})
            assert ok["ok"] and "assessment-week-absence-note" in ok["text"]
            denied = await real_fs.ext_session.call_tool("read_text_file", {"path": "/etc/passwd"})   # the server's own sandbox, as a second layer
            assert denied.isError
    asyncio.run(main())


def test_full_run_reads_documents_through_the_real_server(real_fs):
    task = TASKS["EVAL-02"]

    async def main():
        rid = await go(real_fs, task["learner_id"], task["request"])
        state, result = row(real_fs, rid)
        assert state == "completed" and any("assessment-week-absence-note" in p for p in result["documents_consulted"])
        st = await final_state(real_fs, rid)
        assert "25 minutes" in st["gathered"]["docs"][result["documents_consulted"][0]]["excerpt"]
        assert facts(real_fs, rid).docs_read
    asyncio.run(main())

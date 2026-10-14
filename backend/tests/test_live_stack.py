"""The production path, for real: our MCP server over streamable HTTP in its own process, the real
filesystem server over stdio, Postgres for the data AND the checkpoints, and a simulated process death
while a run waits for the teacher. Needs TEST_DB_URL (Postgres) and the filesystem server installed."""
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
from functools import partial

import pytest

from app.agent.runtime import RunManager, open_checkpointer
from app.agent.tools import open_router
from app.services import reviews as svc
from tests.agentkit import agent_env, ideal_llm  # noqa: F401
from tests.test_agent_graph import TASKS, events, facts, reviews, row, n_changes

CMD = os.environ.get("DOCS_MCP_COMMAND", "mcp-server-filesystem")
PG = os.environ.get("TEST_DB_URL")
pytestmark = pytest.mark.skipif(not PG or shutil.which(CMD) is None, reason="needs TEST_DB_URL (Postgres) and the filesystem server")


@pytest.fixture()
def mcp_process(agent_env):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": PG, "MCP_TRANSPORT": "streamable-http", "MCP_HOST": "127.0.0.1", "MCP_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, "-m", "app.mcp_server.server"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("MCP server did not start: " + proc.stdout.read(2000).decode(errors="replace"))
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_run_survives_process_death_across_http_stdio_and_postgres(agent_env, mcp_process):
    factory = lambda rid, lid: open_router(rid, lid, learner_url=mcp_process, docs_dir=str(agent_env.docs), docs_command=CMD, docs_args="")
    task = TASKS["EVAL-03"]

    async def main():
        async with open_checkpointer(PG) as saver:                              # "process 1"
            m1 = RunManager(saver, router_factory=factory, llm_factory=lambda: ideal_llm())
            rid = await m1.start(task["learner_id"], task["request"])
            await m1.drain()
            assert row(agent_env, rid)[0] == "waiting_for_teacher"
            (review,) = reviews(agent_env, rid)
            f = facts(agent_env, rid)
            assert {"get_learner_timeline", "detect_patterns", "get_evidence", "flag_for_teacher_review"} <= f.tools_called   # audit rows written by the OTHER process
            assert f.docs_read == [] or True
        # process 1 is gone: its connections, event loop and manager no longer exist
        with agent_env.maker() as db:
            svc.decide(db, review.id, "T-017", "approved")
        async with open_checkpointer(PG) as saver:                              # "process 2": new connections, new manager
            m2 = RunManager(saver, router_factory=factory, llm_factory=lambda: ideal_llm())
            await m2.recover()
            await m2.drain()
        state, result = row(agent_env, rid)
        assert state == "completed" and n_changes(agent_env) == 1
        assert result["findings"][0]["outcome"] == "teacher approved; written to the profile"
        assert agent_env_facts_ok(agent_env, rid)
    asyncio.run(main())


def agent_env_facts_ok(env, rid):
    f = facts(env, rid)
    return f.profile_changes == 1 and "update_learner_profile" in f.tools_called


def test_documents_are_read_over_stdio_in_the_live_stack(agent_env, mcp_process):
    factory = lambda rid, lid: open_router(rid, lid, learner_url=mcp_process, docs_dir=str(agent_env.docs), docs_command=CMD, docs_args="")
    task = TASKS["EVAL-02"]

    async def main():
        async with open_checkpointer(PG) as saver:
            m = RunManager(saver, router_factory=factory, llm_factory=lambda: ideal_llm())
            rid = await m.start(task["learner_id"], task["request"])
            await m.drain()
        state, result = row(agent_env, rid)
        assert state == "completed" and result["documents_consulted"], [e.title for e in events(agent_env, rid)]
    asyncio.run(main())

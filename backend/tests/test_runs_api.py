"""The HTTP surface of the agent: start, follow, decide, resume. Runs the real lifespan in a background loop."""
import json
import time
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from tests.agentkit import agent_env  # noqa: F401

REQ_CYNTHIA = {"learner_id": "L1044", "request": "Look at Cynthia's English results over time and tell me whether anything needs my attention."}


@pytest.fixture()
def client(agent_env, monkeypatch):
    import app.main as main

    @asynccontextmanager
    async def fake_checkpointer():
        yield agent_env.saver

    def override():
        with agent_env.maker() as db:
            yield db

    monkeypatch.setattr(main, "open_checkpointer", fake_checkpointer)
    monkeypatch.setattr(main, "RunManager", lambda saver: agent_env.make_manager(saver))
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def wait(client, rid, states, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{rid}").json()
        if run["state"] in states:
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {rid} stuck in {run['state']}; events: {[e['title'] for e in client.get(f'/api/runs/{rid}/events').json()]}")


def test_input_validation_and_unknown_resources(client):
    assert client.post("/api/runs", json={"learner_id": "L9999", "request": "hello there"}).status_code == 404
    assert client.post("/api/runs", json={"learner_id": "L1044", "request": "hi"}).status_code == 422
    assert client.post("/api/runs", json={"learner_id": "L1044", "request": "x" * 501}).status_code == 422
    assert client.post("/api/runs", json={**REQ_CYNTHIA, "extra": 1}).status_code == 422
    for path in ("", "/events", "/stream"):
        assert client.get(f"/api/runs/RUN-NOPE{path}").status_code == 404


def test_runs_are_unavailable_when_the_runtime_is_not_running(agent_env):
    def override():
        with agent_env.maker() as db:
            yield db

    app.dependency_overrides[get_db] = override
    try:
        app.state.runs = None
        assert TestClient(app).post("/api/runs", json=REQ_CYNTHIA).status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_start_follow_decide_resume_over_http(client):
    r = client.post("/api/runs", json=REQ_CYNTHIA)
    assert r.status_code == 202 and r.json()["run_id"].startswith("RUN-")
    rid = r.json()["run_id"]

    run = wait(client, rid, {"waiting_for_teacher", "failed"})
    assert run["state"] == "waiting_for_teacher" and run["result"] is None and len(run["review_ids"]) == 1
    assert run["learner_name"] == "Cynthia Achieng" and run["llm"]["provider"] == "scripted"

    events = client.get(f"/api/runs/{rid}/events").json()
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert {"node", "tool", "llm", "interrupt"} <= {e["kind"] for e in events}
    assert client.get(f"/api/runs/{rid}/events", params={"after": events[-2]["seq"]}).json() == [events[-1]]
    assert rid in [x["run_id"] for x in client.get("/api/runs").json()]

    pending = client.get("/api/reviews").json()
    assert len(pending) == 1 and pending[0]["pattern"]["kind"] == "decline"
    assert client.get("/api/learners/L1044/profile").json() == []

    d = client.post(f"/api/reviews/{run['review_ids'][0]}/decision", json={"teacher_id": "T-017", "decision": "approved", "comment": "Agreed."})
    assert d.status_code == 200
    run = wait(client, rid, {"completed", "failed"})                      # the decision resumed the run in the background
    assert run["state"] == "completed" and run["result"]["summary"]
    assert run["result"]["findings"][0]["outcome"] == "teacher approved; written to the profile"
    profile = client.get("/api/learners/L1044/profile").json()
    assert len(profile) == 1 and profile[0]["pattern"]["kind"] == "decline"
    assert client.get("/api/reviews").json() == []
    assert client.post(f"/api/reviews/{run['review_ids'][0]}/decision", json={"teacher_id": "T-017", "decision": "rejected"}).status_code == 409


def test_event_stream_replays_and_ends(client):
    rid = client.post("/api/runs", json={"learner_id": "L1048", "request": "Is there anything notable in Grace's progress?"}).json()["run_id"]
    assert wait(client, rid, {"completed", "failed"})["state"] == "completed"
    total = len(client.get(f"/api/runs/{rid}/events").json())

    with client.stream("GET", f"/api/runs/{rid}/stream") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    steps = [json.loads(b.split("data: ", 1)[1]) for b in body.split("\n\n") if "event: step" in b]
    assert len(steps) == total and steps[-1]["kind"] == "final"
    assert body.rstrip().endswith('event: end\ndata: {"state": "completed"}')

    with client.stream("GET", f"/api/runs/{rid}/stream", params={"after": steps[-1]["seq"]}) as resp:   # reconnect: only the end marker
        tail = "".join(resp.iter_text())
    assert "event: step" not in tail and "event: end" in tail


def test_a_failed_run_is_reported_over_http(client, monkeypatch):
    import app.mcp_server.tools.get_learner_timeline as tl
    monkeypatch.setattr(tl, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    rid = client.post("/api/runs", json=REQ_CYNTHIA).json()["run_id"]
    run = wait(client, rid, {"failed", "completed"})
    assert run["state"] == "failed" and "Could not read the learner's records" in run["result"]["error"]

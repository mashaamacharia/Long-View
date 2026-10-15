"""Teacher-entered records: the chart feed (GET) and the dashboard's add-record form (POST)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api import learners
from app.db.models import Learner, Observation, Record
from app.db.session import get_db
from tests.dbutil import make_engine

import pytest


@pytest.fixture()
def client():
    engine = make_engine()
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as db:
        db.add(Learner(id="L1042", full_name="Amina Wanjiku", grade_level="Grade 9"))
        db.add(Record(learner_id="L1042", term="2025-T2", kind="quiz", subject="Mathematics",
                      skill="algebra", title="CAT 1", score=62.5, max_score=100))
        db.add(Observation(learner_id="L1042", term="2025-T2", teacher_id="T-01",
                           subject="Mathematics", text="Helped a peer with fractions.", sentiment="strong"))
        db.commit()

    def override():
        with maker() as db:
            yield db

    testapp = FastAPI()
    testapp.include_router(learners.router, prefix="/api")
    testapp.dependency_overrides[get_db] = override
    with TestClient(testapp) as c:
        yield c


def test_records_and_observations_feed_the_charts(client):
    data = client.get("/api/learners/L1042/records").json()
    assert data["records"] == [{
        "id": data["records"][0]["id"], "term": "2025-T2", "kind": "quiz", "subject": "Mathematics",
        "skill": "algebra", "title": "CAT 1", "score": 62.5, "max_score": 100,
        "recorded_on": None, "submitted_late": False, "notes": None,
    }]
    assert data["observations"][0]["text"] == "Helped a peer with fractions."
    assert data["observations"][0]["teacher_id"] == "T-01"
    assert client.get("/api/learners/L9999/records").status_code == 404


def test_create_record_roundtrip(client):
    body = {"term": "2026-T1", "kind": "assignment", "subject": "Science", "skill": "lab_reports",
            "title": "Volcano project write-up", "score": 81, "recorded_on": "2026-02-10", "notes": "Handed in early."}
    created = client.post("/api/learners/L1042/records", json=body)
    assert created.status_code == 201
    row = created.json()
    assert row["term"] == "2026-T1" and row["kind"] == "assignment" and row["score"] == 81
    assert row["recorded_on"] == "2026-02-10" and row["notes"] == "Handed in early."

    listed = client.get("/api/learners/L1042/records").json()["records"]
    assert any(r["id"] == row["id"] and r["title"] == "Volcano project write-up" for r in listed)


def test_create_record_validation(client):
    good = {"term": "2026-T1", "kind": "quiz", "subject": "English"}
    assert client.post("/api/learners/L9999/records", json=good).status_code == 404
    assert client.post("/api/learners/L1042/records", json={**good, "kind": "exam"}).status_code == 422
    assert client.post("/api/learners/L1042/records", json={**good, "term": "Term 1"}).status_code == 422
    assert client.post("/api/learners/L1042/records", json={**good, "score": 101}).status_code == 422
    assert client.post("/api/learners/L1042/records", json={**good, "extra": 1}).status_code == 422
    assert client.post("/api/learners/L1042/records", json={}).status_code == 422

"""Tests for the deterministic analysis layer.

Three levels: unit tests per module, persona tests driven by the `checks` in evals/tasks/*.yaml
(so the eval specs are also the oracle for the analysis), and tool-level persistence tests.
"""
import json
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Evidence, LearnerPattern
from app.db.seed import seed
from app.mcp_server.analysis import conflicts as cf
from app.mcp_server.analysis import outliers as ol
from app.mcp_server.analysis import sufficiency as sf
from app.mcp_server.analysis import trends as tr
from app.mcp_server.analysis.common import dedupe, missing_terms, pct, term_label, term_ord
from app.mcp_server.analysis.engine import analyse
from tests.dbutil import make_engine
from data_gen.generate import build_dataset

TASKS = Path(__file__).resolve().parents[1] / "evals" / "tasks"


# ---------- common ----------
def test_term_arithmetic():
    assert term_label(term_ord("2025-T2")) == "2025-T2"
    assert term_ord("2025-T1") - term_ord("2024-T3") == 1  # consecutive across a year boundary
    with pytest.raises(ValueError):
        term_ord("2025-T4")


def test_pct_normalises_and_handles_blanks():
    assert pct({"score": 7, "max_score": 10}) == 70.0
    assert pct({"score": 35, "max_score": 50}) == 70.0
    assert pct({"score": None, "max_score": 10}) is None
    assert pct({"score": 5, "max_score": 0}) is None


def test_dedupe_counts_repeats_once():
    a = {"term": "2024-T1", "kind": "quiz", "subject": "S", "skill": "k", "title": "t", "score": 5, "max_score": 10, "source": "x"}
    b = {**a, "source": "y"}
    c = {**a, "title": "other"}
    kept, dropped = dedupe([a, b, c])
    assert len(kept) == 2 and len(dropped) == 1


def test_missing_terms_only_inside_span():
    o = [term_ord(t) for t in ("2024-T2", "2025-T2")]
    assert missing_terms(o) == ["2024-T3", "2025-T1"]
    assert missing_terms([]) == []


# ---------- trends ----------
def test_theil_sen_recovers_line_and_ignores_stray_point():
    xs = list(range(12))
    ys = [50 + 3 * x for x in xs]
    ys[5] = 5  # one wild point
    slope, intercept = tr.theil_sen([float(x) for x in xs], ys)
    assert slope == pytest.approx(3, abs=0.2) and intercept == pytest.approx(50, abs=1)


def test_mann_kendall_monotone_vs_flat():
    assert tr.mann_kendall([1, 2, 3, 4, 5, 6, 7, 8])["p"] < 0.01
    assert tr.mann_kendall([5, 6, 5, 6, 5, 6, 5, 6])["p"] > 0.3
    assert tr.mann_kendall([1, 2])["p"] == 1.0


def _points(vals, start="2023-T1"):
    return [{"ord": term_ord(start) + i, "term": term_label(term_ord(start) + i), "mean": v, "n": 3} for i, v in enumerate(vals)]


def test_trend_detects_direction_and_requires_practical_change():
    assert tr.trend(_points([50, 54, 58, 62, 66, 70, 74]))["direction"] == "up"
    assert tr.trend(_points([80, 75, 70, 64, 58, 52]))["direction"] == "down"
    assert tr.trend(_points([60, 61, 60, 62, 61, 62, 61, 62]))["direction"] == "none"  # tiny, even if monotone-ish
    assert tr.trend(_points([60, 70]))["direction"] == "none"  # under 3 terms


def test_trend_needs_significance_not_just_a_big_swing():
    # early vs late differs by 10 points and the slope is negative, but the series is erratic:
    # without the Mann-Kendall gate this would be reported as a decline.
    t = tr.trend(_points([55, 80, 65, 65, 70, 55, 60, 55]))
    assert abs(t["change"]) >= tr.MIN_CHANGE and abs(t["slope"]) >= tr.MIN_SLOPE
    assert t["p_value"] > tr.ALPHA and t["direction"] == "none"


def test_trend_respects_gaps_in_the_calendar():
    pts = _points([50, 54, 58, 62], "2023-T1") + _points([70, 74, 78], "2025-T1")  # a gap of 4 terms
    t = tr.trend(pts)
    assert t["direction"] == "up" and t["n_terms"] == 7


# ---------- outliers ----------
def _rows(vals, kind="quiz", start=0):
    return [{"ord": 100 + start + i // 2, "pct": v, "kind": kind} for i, v in enumerate(vals)]


def test_outlier_single_wild_point_flagged():
    vals = [70, 72, 69, 71, 73, 70, 68, 72, 71, 22, 70, 73, 69, 71, 72, 70]
    out = ol.detect_outliers(_rows(vals))
    assert len(out) == 1 and out[0]["pct"] == 22 and out[0]["residual"] < -40


def test_outlier_clean_trending_series_not_flagged():
    vals = [50 + 3 * (i // 2) + (i % 2) * 2 for i in range(20)]
    assert ol.detect_outliers(_rows(vals)) == []


def test_outlier_needs_enough_data_and_a_big_miss():
    assert ol.detect_outliers(_rows([70, 71, 22, 70])) == []            # too few records
    vals = [70, 72, 69, 71, 73, 70, 68, 72, 71, 58, 70, 73, 69, 71]      # a 12 point dip is ordinary
    assert ol.detect_outliers(_rows(vals)) == []


def test_kind_class():
    assert ol.kind_class("quiz") == "quiz" and ol.kind_class("project") == "coursework"


# ---------- sufficiency ----------
def test_classify_rules():
    assert sf.classify(2, 4, 2, []) == "none"
    assert sf.classify(3, 20, 2, []) == "none"          # under 4 terms
    assert sf.classify(5, 6, 2, []) == "none"           # under 8 records
    assert sf.classify(5, 12, 2, []) == "medium"        # short
    assert sf.classify(9, 24, 1, []) == "medium"        # one channel only
    assert sf.classify(9, 24, 2, ["2024-T3"]) == "medium"  # a gap caps strength
    assert sf.classify(9, 24, 2, []) == "high"


# ---------- conflicts ----------
@pytest.mark.parametrize("text,expected", [
    ("Lazy in class and rushes his written work.", True),
    ("Slow learner who needs constant pushing.", True),
    ("Not an academic child; better suited to hands-on subjects.", True),
    ("Seems gifted in maths.", True),
    ("Slow to start but finishes carefully.", False),
    ("Explains her working to a partner.", False),
    ("", False),
])
def test_label_language(text, expected):
    assert cf.has_label_language(text) is expected


def _gap_rows(quiz, work):
    rows = []
    for i in range(6):
        rows.append({"ord": i, "pct": quiz, "kind": "quiz"})
        rows.append({"ord": i, "pct": work, "kind": "assignment"})
    return rows


def test_assessment_type_gap():
    assert cf.assessment_type_gap(_gap_rows(48, 86))["gap"] == pytest.approx(38)
    assert cf.assessment_type_gap(_gap_rows(70, 74)) is None            # similar
    assert cf.assessment_type_gap(_gap_rows(48, 86)[:6]) is None         # too little on one side


# ---------- engine ----------
@pytest.fixture(scope="module")
def ds():
    return build_dataset()


def run(ds, lid, **kw):
    return analyse(lid, ds["records"], ds["observations"], **kw)


def test_engine_is_deterministic_and_ids_are_stable(ds):
    a, b = run(ds, "L1043"), run(ds, "L1043")
    assert a == b
    assert [p["pattern_id"] for p in a["patterns"]] == [p["pattern_id"] for p in b["patterns"]]


def test_subject_filter(ds):
    r = run(ds, "L1042", subject="English")
    assert r["patterns"] == [] and {c["subject"] for c in r["checked"]} == {"English"}


def test_no_scored_data_is_insufficient():
    r = analyse("LX", [], [])
    assert [p["kind"] for p in r["patterns"]] == ["insufficient"] and r["patterns"][0]["subtype"] == "no_scored_data"


# ---------- persona tests, driven by the eval specs ----------
EXPECTED = {
    "L1042": {("strength", "Mathematics", "problem_solving")},
    "L1043": {("anomaly", "Science", "concepts")},
    "L1044": {("decline", "English", "reading_comprehension")},
    "L1045": {("conflict", "Mathematics", "problem_solving")},
    "L1046": {("insufficient", "Mathematics", "number_fluency")},
    "L1047": {("strength", "English", "writing")},
    "L1048": set(),
    "L1049": {("strength", "Science", "practical_work"), ("conflict", "Science", "practical_work")},
}


@pytest.mark.parametrize("lid", sorted(EXPECTED))
def test_exact_pattern_set_per_persona(ds, lid):
    got = {(p["kind"], p["subject"], p["skill"]) for p in run(ds, lid)["patterns"]}
    assert got == EXPECTED[lid]


RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
AGENT_LEVEL = {"flagged_for_review", "tools_called", "tools_not_called", "documents_consulted",
               "max_evidence_loops", "profile_changes_written", "unapproved_update_rejected_or_not_attempted",
               "teacher_decision", "audit_contains"}


def _match(p, spec):
    for k, v in spec.items():
        if k == "evidence_strength_at_most":
            if RANK[p["evidence_strength"]] > RANK[v]:
                return False
        elif p.get(k) != v:
            return False
    return True


def _persona_tasks():
    out = []
    for f in sorted(TASKS.glob("*.yaml")):
        t = yaml.safe_load(f.read_text())
        if {"patterns_include", "patterns_exclude"} & set(t["checks"]):
            out.append(pytest.param(t, id=t["id"]))
    return out


@pytest.mark.parametrize("task", _persona_tasks())
def test_eval_checks_hold_for_the_analysis_layer(ds, task):
    checks, lid = task["checks"], task["learner_id"]
    unknown = set(checks) - AGENT_LEVEL - {
        "patterns_include", "patterns_exclude", "min_evidence_terms", "anomaly_flagged", "corroboration",
        "acknowledges_gap", "duplicates_not_double_counted", "must_not_assert_labels", "notes_data_mismatch_flagged"}
    assert not unknown, f"{task['id']} has checks the analysis tests do not understand: {unknown}"

    r = run(ds, lid)
    pats = r["patterns"]
    matched = []
    for spec in checks.get("patterns_include", []):
        hits = [p for p in pats if _match(p, spec)]
        assert hits, f"{task['id']}: expected a pattern matching {spec}"
        matched += hits
    for spec in checks.get("patterns_exclude", []):
        assert not [p for p in pats if _match(p, spec)], f"{task['id']}: unexpected pattern matching {spec}"

    if "min_evidence_terms" in checks:
        assert all(p["n_terms"] >= checks["min_evidence_terms"] for p in matched)
    if "anomaly_flagged" in checks:
        assert any(p["kind"] == "anomaly" and p["detail"]["term"] == checks["anomaly_flagged"]["term"] for p in pats)
    if "corroboration" in checks:
        want = {"observations": "teacher_observations"}.get
        for p in matched:
            assert all(want(c, c) in p["channels"] for c in checks["corroboration"])
    if "acknowledges_gap" in checks:
        for g in checks["acknowledges_gap"]:
            assert g in r["data_quality"]["terms_missing_within_span"]
            assert any(g in c for p in matched for c in p["caveats"])
    if checks.get("duplicates_not_double_counted"):
        assert r["data_quality"]["duplicates_removed"] >= 1
        for p in matched:
            unique = {(x["term"], x["kind"], x["subject"], x["skill"], x["title"], x["score"], x["max_score"])
                      for x in ds["records"] if x["learner_id"] == lid and x["subject"] == p["subject"]
                      and x["skill"] == p["skill"] and x["score"] is not None}
            assert p["n_records"] == len(unique)
    if "must_not_assert_labels" in checks:
        text = " ".join([p["statement"] for p in pats] + [c for p in pats for c in p["caveats"]]).lower()
        assert not [w for w in checks["must_not_assert_labels"] if w in text]
    if checks.get("notes_data_mismatch_flagged"):
        assert any(p["kind"] == "conflict" and p["subtype"] == "label_language" for p in pats)


def test_every_pattern_carries_evidence_and_no_cause_language(ds):
    banned = ["because", "due to", "caused", "anxiety", "dyslex", "lazy", "ability"]
    for lid in EXPECTED:
        for p in run(ds, lid)["patterns"]:
            assert p["evidence"] or p["kind"] == "insufficient"
            assert not [w for w in banned if w in p["statement"].lower()], (lid, p["statement"])


def test_anomaly_pulls_in_same_term_context(ds):
    p = next(p for p in run(ds, "L1043")["patterns"] if p["kind"] == "anomaly")
    types = {e["type"] for e in p["evidence"]}
    assert types == {"record", "observation"} or "attendance" in p["channels"]
    assert "attendance" in p["channels"] and "teacher_observations" in p["channels"]
    assert p["evidence_strength"] == "medium"


# ---------- tool level (SQLite stand-in for Postgres) ----------
@pytest.fixture()
def tool(ds, monkeypatch):
    engine = make_engine()
    with Session(engine) as db:
        seed(db, ds)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    import app.mcp_server.tools.detect_patterns as mod
    monkeypatch.setattr(mod, "SessionLocal", maker)
    return mod, maker


def test_tool_returns_compact_json_safe_summary(tool):
    mod, _ = tool
    out = mod.detect_patterns("L1044")
    json.dumps(out)  # the audit decorator stores this as JSON
    assert out["ok"] and out["patterns"][0]["kind"] == "decline"
    p = out["patterns"][0]
    assert p["evidence_counts"]["records"] > 10 and "records" not in p  # counts, not a dump
    assert p["term_means"][0][0] == "2023-T1" and p["status"] == "proposed"
    assert len(json.dumps(out)) < 6000  # small enough for a 4B model's context


def test_tool_unknown_learner_and_empty_result(tool):
    mod, _ = tool
    assert mod.detect_patterns("NOPE")["ok"] is False
    grace = mod.detect_patterns("L1048")
    assert grace["ok"] and grace["patterns"] == [] and len(grace["checked"]) == 3


def test_tool_persists_evidence_and_is_idempotent(tool):
    mod, maker = tool
    first = mod.detect_patterns("L1043")
    second = mod.detect_patterns("L1043")
    assert [p["pattern_id"] for p in first["patterns"]] == [p["pattern_id"] for p in second["patterns"]]
    with maker() as db:
        assert db.scalar(select(func.count()).select_from(LearnerPattern)) == 1
        pid = first["patterns"][0]["pattern_id"]
        n_ev = db.scalar(select(func.count()).select_from(Evidence).where(Evidence.pattern_id == pid))
        assert n_ev == first["patterns"][0]["evidence_counts"]["records"] + first["patterns"][0]["evidence_counts"]["observations"]
        row = db.get(LearnerPattern, pid)
        assert row.subject == "Science" and row.detail["subtype"] == "single_score" and row.confidence is None


def test_reviewed_patterns_are_not_overwritten(tool):
    mod, maker = tool
    pid = mod.detect_patterns("L1044")["patterns"][0]["pattern_id"]
    with maker() as db:
        row = db.get(LearnerPattern, pid)
        row.status, row.statement = "approved", "teacher-approved wording"
        db.commit()
        n_before = db.scalar(select(func.count()).select_from(Evidence).where(Evidence.pattern_id == pid))
    again = mod.detect_patterns("L1044")["patterns"][0]
    assert again["status"] == "approved"
    with maker() as db:
        assert db.get(LearnerPattern, pid).statement == "teacher-approved wording"
        assert db.scalar(select(func.count()).select_from(Evidence).where(Evidence.pattern_id == pid)) == n_before

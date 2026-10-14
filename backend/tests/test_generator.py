from collections import defaultdict
from statistics import mean

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Learner, Observation, Record
from app.db.seed import seed
from tests.dbutil import make_engine
from data_gen.generate import ALL_TERMS, build_dataset, load_personas, validate_persona


@pytest.fixture(scope="module")
def ds():
    return build_dataset()


def pct(r):
    return None if r["score"] is None else r["score"] / r["max_score"] * 100


def recs(ds, lid, **kw):
    out = [r for r in ds["records"] if r["learner_id"] == lid]
    for k, v in kw.items():
        out = [r for r in out if r[k] == v] if not isinstance(v, (list, set)) else [r for r in out if r[k] in v]
    return out


def term_means(rows):
    by = defaultdict(list)
    for r in rows:
        if pct(r) is not None:
            by[r["term"]].append(pct(r))
    return {t: mean(v) for t, v in sorted(by.items())}


def test_deterministic():
    assert build_dataset() == build_dataset()


def test_shape(ds):
    assert len(ds["learners"]) == 8
    assert len(ds["documents"]) >= 6
    assert all(r["max_score"] > 0 for r in ds["records"])


def test_amina_strength_is_skill_specific(ds):
    ps = term_means(recs(ds, "L1042", skill="problem_solving"))
    terms = list(ps)
    assert len(terms) == 11
    assert mean(ps[t] for t in terms[-3:]) - mean(ps[t] for t in terms[:3]) > 15
    nf = term_means(recs(ds, "L1042", skill="number_fluency"))
    assert abs(mean(list(nf.values())[-3:]) - mean(list(nf.values())[:3])) < 8


def test_brian_has_exactly_one_outlier(ds):
    sci = [r for r in recs(ds, "L1043", skill="concepts") if pct(r) is not None]
    low = [r for r in sci if pct(r) < 40]
    assert len(low) == 1 and low[0]["term"] == "2025-T2"
    others = [pct(r) for r in sci if r is not low[0]]
    assert mean(others) > 65


def test_cynthia_decline_is_skill_specific(ds):
    rc = term_means(recs(ds, "L1044", skill="reading_comprehension"))
    v = list(rc.values())
    assert mean(v[:6]) - mean(v[-3:]) > 12
    wr = list(term_means(recs(ds, "L1044", skill="writing")).values())
    assert abs(mean(wr[:6]) - mean(wr[-3:])) < 8
    att = [r["score"] for r in recs(ds, "L1044", kind="attendance")]
    assert att[0] - att[-1] > 12


def test_david_conflict(ds):
    quiz = [pct(r) for r in recs(ds, "L1045", skill="problem_solving", kind="quiz") if pct(r) is not None]
    open_ = [pct(r) for r in recs(ds, "L1045", skill="problem_solving", kind=["assignment", "project"]) if pct(r) is not None]
    assert mean(open_) - mean(quiz) > 25


def test_esther_is_insufficient(ds):
    rows = [r for r in recs(ds, "L1046") if r["kind"] != "attendance"]
    assert {r["term"] for r in rows} == {"2026-T1", "2026-T2"}
    assert len(rows) <= 4


def test_farouk_gaps_blanks_duplicates(ds):
    rows = recs(ds, "L1047")
    terms = {r["term"] for r in rows}
    assert "2024-T3" not in terms and "2025-T1" not in terms
    assert any(r["score"] is None for r in rows)
    assert len({r["max_score"] for r in rows if r["kind"] != "attendance"}) > 2
    seen = defaultdict(int)
    for r in rows:
        seen[(r["term"], r["title"], r["score"])] += 1
    assert sum(1 for c in seen.values() if c > 1) >= 1


def test_grace_is_flat(ds):
    for skill in ("number_fluency", "reading_comprehension", "concepts"):
        v = list(term_means(recs(ds, "L1048", skill=skill)).values())
        assert abs(mean(v[-4:]) - mean(v[:4])) < 6


def test_ian_labels_vs_data(ds):
    pw = list(term_means(recs(ds, "L1049", skill="practical_work")).values())
    assert mean(pw[-3:]) - mean(pw[:3]) > 15
    texts = " ".join(o["text"] for o in ds["observations"] if o["learner_id"] == "L1049").lower()
    assert "lazy" in texts and "slow learner" in texts


def test_documents_have_unique_paths(ds):
    paths = [d["path"] for d in ds["documents"]]
    assert len(paths) == len(set(paths))


def test_validation_rejects_bad_means():
    p = load_personas()[0]
    p["series"][0]["means"] = [50, 60]
    with pytest.raises(ValueError):
        validate_persona(p)


def test_seed_roundtrip_and_idempotence(ds):
    engine = make_engine()
    with Session(engine) as db:
        r1 = seed(db, ds)
        assert r1["learners"] == 8 and r1["records"] == len(ds["records"])
        assert db.scalar(select(func.count()).select_from(Observation)) == len(ds["observations"])
        assert seed(db, ds)["skipped"] is True
        assert seed(db, ds, reset=True)["skipped"] is False
        assert db.scalar(select(func.count()).select_from(Learner)) == 8
        assert db.scalar(select(func.count()).select_from(Record)) == len(ds["records"])

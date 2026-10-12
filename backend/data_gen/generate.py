"""Seeded synthetic learner data generator.

Personas live in data_gen/personas/*.yaml. Each persona plants a known pattern (strength, decline,
single anomaly, conflict, insufficient data, gaps, no pattern, label bait) so every eval has a
known right answer. Output is fully deterministic for a given SEED.

Usage (from backend/):
    python -m data_gen.generate                      # print a summary
    python -m data_gen.generate --write-docs         # write teacher documents to DOCS_DIR
    python -m data_gen.generate --export-tasks       # write eval task specs to evals/tasks/
"""
from __future__ import annotations

import argparse
import os
import random
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

SEED = 42
PERSONA_DIR = Path(__file__).parent / "personas"
ALL_TERMS = [f"{y}-T{t}" for y in (2023, 2024, 2025, 2026) for t in (1, 2, 3)][:11]  # to 2026-T2
TERM_START = {"T1": (1, 20), "T2": (5, 6), "T3": (9, 2)}  # Kenyan three-term year (approximate)
MAX_SCORES = {"quiz": [10, 20, 25], "assignment": [20, 50, 100], "project": [50, 100]}
SOURCES = ["gradebook_export", "teacher_sheet", "lms_import"]
SOURCE_WEIGHTS = [5, 3, 2]


# ---------- helpers ----------
def term_start(term: str) -> date:
    year, t = term.split("-")
    month, day = TERM_START[t]
    return date(int(year), month, day)


def _clamp(x: float, lo: float = 5.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def load_personas(persona_dir: Path = PERSONA_DIR) -> list[dict[str, Any]]:
    personas = [yaml.safe_load(p.read_text()) for p in sorted(persona_dir.glob("*.yaml"))]
    for p in personas:
        validate_persona(p)
    ids = [p["id"] for p in personas]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate persona ids")
    return personas


def active_terms(p: dict[str, Any]) -> list[str]:
    first, last = p["terms"]
    i, j = ALL_TERMS.index(first), ALL_TERMS.index(last)
    skip = set(p.get("skip_terms", []))
    return [t for t in ALL_TERMS[i : j + 1] if t not in skip]


def validate_persona(p: dict[str, Any]) -> None:
    pid = p.get("id", "?")
    for key in ("id", "full_name", "grade_level", "scenario", "terms"):
        if key not in p:
            raise ValueError(f"{pid}: missing '{key}'")
    for t in p["terms"] + p.get("skip_terms", []):
        if t not in ALL_TERMS:
            raise ValueError(f"{pid}: unknown term {t}")
    n = len(active_terms(p))
    for s in p.get("series", []):
        if "means" in s and len(s["means"]) != n:
            raise ValueError(f"{pid}: {s['subject']}/{s['skill']} means has {len(s['means'])} values, need {n}")
        for k in s["kinds"]:
            if k not in MAX_SCORES:
                raise ValueError(f"{pid}: unknown kind {k}")
    att = p.get("attendance") or {}
    if "means" in att and len(att["means"]) != n:
        raise ValueError(f"{pid}: attendance means has {len(att['means'])} values, need {n}")
    for o in p.get("observations", []):
        if o["term"] not in ALL_TERMS:
            raise ValueError(f"{pid}: observation in unknown term {o['term']}")
    for d in p.get("documents", []):
        if d["term"] not in ALL_TERMS:
            raise ValueError(f"{pid}: document in unknown term {d['term']}")


def _means(spec: dict[str, Any], n: int) -> list[float]:
    if "means" in spec:
        return list(spec["means"])
    return [spec["base"] + spec.get("slope", 0) * i for i in range(n)]


# ---------- generation ----------
def _series_records(rng: random.Random, p: dict[str, Any], s: dict[str, Any], terms: list[str]) -> list[dict]:
    means = _means(s, len(terms))
    anomalies = {(a["term"], a["index"]): a for a in s.get("anomalies", [])}
    miss = p.get("missing_score_rate", 0.03)
    late_rate = p.get("late_rate", 0.08)
    out: list[dict] = []
    for ti, term in enumerate(terms):
        n = s.get("n_per_term", 3)
        offsets = sorted(rng.sample(range(5, 85), n))
        for j in range(n):
            kind = rng.choice(s["kinds"])
            max_score = rng.choice(MAX_SCORES[kind])
            pct = _clamp(rng.gauss(means[ti], s.get("noise", 4)))
            missing = rng.random() < miss
            late = rng.random() < late_rate if kind != "quiz" else False
            source = rng.choices(SOURCES, SOURCE_WEIGHTS)[0]
            title = s.get("title") or f"{s['subject']} {kind}"
            a = anomalies.get((term, j))
            if a:
                pct = a["pct"]
                kind = a.get("kind", kind)
                max_score = a.get("max_score", max_score)
                title = a.get("title", title)
                missing = False
            score = None if missing else min(max_score, round(pct / 100 * max_score * 2) / 2)
            out.append(
                {
                    "learner_id": p["id"],
                    "term": term,
                    "kind": kind,
                    "subject": s["subject"],
                    "skill": s.get("skill"),
                    "title": f"{title} ({term} #{j + 1})",
                    "score": score,
                    "max_score": float(max_score),
                    "recorded_on": term_start(term) + timedelta(days=offsets[j]),
                    "submitted_late": late,
                    "source": source,
                    "notes": None,
                }
            )
    return out


def _attendance_records(rng: random.Random, p: dict[str, Any], terms: list[str]) -> list[dict]:
    att = p.get("attendance")
    if not att:
        return []
    means = _means(att, len(terms))
    overrides = att.get("overrides", {})
    out = []
    for ti, term in enumerate(terms):
        pct = overrides.get(term, _clamp(rng.gauss(means[ti], att.get("noise", 2)), 40, 100))
        out.append(
            {
                "learner_id": p["id"],
                "term": term,
                "kind": "attendance",
                "subject": "All",
                "skill": None,
                "title": f"Term attendance % ({term})",
                "score": round(float(pct), 1),
                "max_score": 100.0,
                "recorded_on": term_start(term) + timedelta(days=85),
                "submitted_late": False,
                "source": "attendance_register",
                "notes": None,
            }
        )
    return out


def build_dataset(personas: list[dict[str, Any]] | None = None) -> dict[str, list[dict]]:
    personas = personas if personas is not None else load_personas()
    learners, records, observations, documents = [], [], [], []
    for p in personas:
        rng = random.Random(f"{SEED}:{p['id']}")  # string seeds are stable across runs
        terms = active_terms(p)
        learners.append({"id": p["id"], "full_name": p["full_name"], "grade_level": p["grade_level"]})

        recs: list[dict] = []
        for s in p.get("series", []):
            recs.extend(_series_records(rng, p, s, terms))
        scored = [r for r in recs]  # non-attendance rows eligible for duplication
        for r in rng.sample(scored, min(p.get("duplicates", 0), len(scored))):
            dup = dict(r)
            dup["source"] = "lms_import" if r["source"] != "lms_import" else "gradebook_export"
            recs.append(dup)
        recs.extend(_attendance_records(rng, p, terms))
        recs.sort(key=lambda r: (r["term"], r["recorded_on"], r["subject"], r["title"]))
        records.extend(recs)

        for o in p.get("observations", []):
            observations.append(
                {
                    "learner_id": p["id"],
                    "term": o["term"],
                    "teacher_id": o["teacher"],
                    "subject": o.get("subject"),
                    "skill": o.get("skill"),
                    "sentiment": o.get("sentiment"),
                    "text": o["text"],
                    "recorded_on": term_start(o["term"]) + timedelta(days=70),
                }
            )
        for d in p.get("documents", []):
            slug = re.sub(r"[^a-z0-9]+", "-", d["title"].lower()).strip("-")
            documents.append(
                {
                    "learner_id": p["id"],
                    "term": d["term"],
                    "type": d["type"],
                    "author": d["author"],
                    "title": d["title"],
                    "body": d["body"].strip() + "\n",
                    "path": f"{p['id']}/{d['term']}_{slug}.md",
                }
            )
    return {"learners": learners, "records": records, "observations": observations, "documents": documents}


# ---------- outputs ----------
def write_docs(dataset: dict[str, list[dict]], docs_dir: Path) -> int:
    for d in dataset["documents"]:
        path = docs_dir / d["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            f"learner_id: {d['learner_id']}\n"
            f"term: {d['term']}\n"
            f"document_type: {d['type']}\n"
            f"author: {d['author']}\n"
            f"title: {d['title']}\n"
            "---\n\n"
            f"{d['body']}"
        )
    return len(dataset["documents"])


def export_eval_tasks(personas: list[dict[str, Any]], out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in personas:
        ev = p.get("eval")
        if not ev:
            continue
        task = {
            "id": ev["id"],
            "name": ev["name"],
            "learner_id": p["id"],
            "scenario": p["scenario"],
            "request": ev["request"],
            "expect": ev["expect"],
            "must_not": ev["must_not"],
            "checks": ev["checks"],
        }
        path = out_dir / f"{ev['id'].lower()}_{p['scenario']}.yaml"
        header = f"# Generated from data_gen/personas/{p['id']}_*.yaml. Edit the persona file, then re-export.\n"
        path.write_text(header + yaml.safe_dump(task, sort_keys=False, allow_unicode=True, width=100))
        n += 1
    return n


def summarise(dataset: dict[str, list[dict]]) -> str:
    lines = []
    for l in dataset["learners"]:
        recs = [r for r in dataset["records"] if r["learner_id"] == l["id"]]
        terms = sorted({r["term"] for r in recs})
        n_obs = sum(1 for o in dataset["observations"] if o["learner_id"] == l["id"])
        n_doc = sum(1 for d in dataset["documents"] if d["learner_id"] == l["id"])
        lines.append(f"{l['id']} {l['full_name']:<16} terms={len(terms):<2} records={len(recs):<3} obs={n_obs} docs={n_doc}")
    lines.append(
        f"TOTAL learners={len(dataset['learners'])} records={len(dataset['records'])} "
        f"observations={len(dataset['observations'])} documents={len(dataset['documents'])}"
    )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs-dir", default=os.environ.get("DOCS_DIR", "/data/docs"))
    ap.add_argument("--tasks-dir", default=str(Path(__file__).resolve().parents[1] / "evals" / "tasks"))
    ap.add_argument("--write-docs", action="store_true")
    ap.add_argument("--export-tasks", action="store_true")
    args = ap.parse_args()

    personas = load_personas()
    dataset = build_dataset(personas)
    print(summarise(dataset))
    if args.write_docs:
        print(f"wrote {write_docs(dataset, Path(args.docs_dir))} documents to {args.docs_dir}")
    if args.export_tasks:
        print(f"wrote {export_eval_tasks(personas, Path(args.tasks_dir))} eval tasks to {args.tasks_dir}")


if __name__ == "__main__":
    main()

"""Load synthetic data into Postgres (and write teacher documents for the external MCP).

    make seed          # seed if the database has no records yet
    make seed-reset    # wipe ALL tables (including patterns and audit) and reseed
"""
import argparse
import os
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Learner, Observation, Record
from app.db.session import SessionLocal
from data_gen.generate import build_dataset, write_docs


def _reset(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    else:  # sqlite (tests)
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())


def seed(db: Session, dataset: dict, reset: bool = False) -> dict:
    if reset:
        _reset(db)
    elif (db.scalar(select(func.count()).select_from(Record)) or 0) > 0:
        return {"skipped": True}
    db.add_all(Learner(**l) for l in dataset["learners"])
    db.flush()
    db.add_all(Record(**r) for r in dataset["records"])
    db.add_all(Observation(**o) for o in dataset["observations"])
    db.commit()
    return {
        "skipped": False,
        "learners": len(dataset["learners"]),
        "records": len(dataset["records"]),
        "observations": len(dataset["observations"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe every table first")
    args = ap.parse_args()

    dataset = build_dataset()
    with SessionLocal() as db:
        result = seed(db, dataset, reset=args.reset)
    if result["skipped"]:
        print("Database already has records. Use `make seed-reset` to wipe and reseed.")
        return
    print(f"Seeded {result['learners']} learners, {result['records']} records, {result['observations']} observations.")

    docs_dir = Path(os.environ.get("DOCS_DIR", "/data/docs"))
    try:
        print(f"Wrote {write_docs(dataset, docs_dir)} documents to {docs_dir}")
    except OSError as exc:
        print(f"Could not write documents to {docs_dir}: {exc}")


if __name__ == "__main__":
    main()

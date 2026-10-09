"""Load synthetic data. Run: make seed

TODO: call data_gen/generate.py output and insert learners, records, observations.
"""
from app.db.models import Learner
from app.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        if db.get(Learner, "L1042") is None:
            db.add(Learner(id="L1042", full_name="Amina Wanjiku", grade_level="Grade 8"))
            db.commit()
            print("Seeded placeholder learner L1042 (replace with data_gen output).")
        else:
            print("Already seeded.")


if __name__ == "__main__":
    main()

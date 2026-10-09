def detect_patterns(learner_id: str, subject: str | None = None) -> dict:
    """Deterministic pattern detection. TODO: use analysis/{trends,outliers,sufficiency,conflicts}.

    Must: require multiple terms, reject single anomalous scores, report insufficient data
    instead of guessing, and describe evidence strength (never a label for the learner).
    """
    return {"learner_id": learner_id, "patterns": [], "note": "not implemented"}

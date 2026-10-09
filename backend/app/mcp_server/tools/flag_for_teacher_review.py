def flag_for_teacher_review(learner_id: str, pattern_id: str, reason: str) -> dict:
    """Create a pending teacher review. TODO: insert TeacherReview row."""
    return {"learner_id": learner_id, "pattern_id": pattern_id, "status": "pending", "note": "not implemented"}

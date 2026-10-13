from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.reviews import DecisionIn
from app.services import reviews as svc

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _http(exc: svc.ReviewError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.get("")
def list_reviews(status: str = "pending", db: Session = Depends(get_db)) -> list[dict]:
    """Reviews waiting for a teacher (default), or filter by status."""
    try:
        return svc.list_reviews(db, status)
    except svc.ReviewError as exc:
        raise _http(exc)


@router.get("/{review_id}")
def get_review(review_id: int, db: Session = Depends(get_db)) -> dict:
    """Everything a teacher needs to decide: the finding, full evidence, original notes, decision history."""
    try:
        return svc.review_detail(db, review_id)
    except svc.ReviewError as exc:
        raise _http(exc)


@router.post("/{review_id}/decision")
def decide(review_id: int, body: DecisionIn, db: Session = Depends(get_db)) -> dict:
    """Approve, reject, or ask for more evidence. Approval mints the approval_id that unlocks the profile write."""
    try:
        return svc.decide(db, review_id, body.teacher_id, body.decision, body.comment)
    except svc.ReviewError as exc:
        raise _http(exc)

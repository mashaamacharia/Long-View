from fastapi import APIRouter

router = APIRouter(prefix="/reviews", tags=["reviews"])

# TODO: GET  /reviews                 -> pending teacher reviews
# TODO: POST /reviews/{id}/decision   -> approve | reject | more_evidence
#       Approve must create an Approval row; its id is what unlocks update_learner_profile.


@router.get("/ping")
def ping() -> dict:
    return {"reviews": "ok"}

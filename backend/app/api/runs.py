from fastapi import APIRouter

router = APIRouter(prefix="/runs", tags=["runs"])

# TODO: POST /runs            -> start an agent run for a learner + request
# TODO: GET  /runs/{id}/stream -> SSE stream of tool calls / agent state for the UI


@router.get("/ping")
def ping() -> dict:
    return {"runs": "ok"}

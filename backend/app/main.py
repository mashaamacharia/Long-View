from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import learners, reviews, runs
from app.config import settings

app = FastAPI(title="LongView API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(learners.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")

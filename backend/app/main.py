from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.runtime import RunManager, open_checkpointer

from app.api import learners, reviews, runs
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with open_checkpointer() as saver:
        manager = RunManager(saver)
        manager.attach_loop()
        app.state.runs = manager
        await manager.recover()
        yield
        await manager.drain()
        app.state.runs = None


app = FastAPI(title="LongView API", version="0.1.0", lifespan=lifespan)

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

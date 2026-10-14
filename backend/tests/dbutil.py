"""Test database factory. Default: in-memory SQLite. Set TEST_DB_URL to run the same tests on Postgres:

    TEST_DB_URL=postgresql+psycopg://longview:longview@localhost:5432/longview_test pytest

The target database is wiped (drop_all/create_all) for every test, so point it at a scratch database.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base


def make_engine():
    url = os.environ.get("TEST_DB_URL")
    if url:
        engine = create_engine(url, pool_pre_ping=True)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        return engine
    # TestClient serves requests on another thread; one shared connection keeps a single in-memory DB
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def is_postgres() -> bool:
    return bool(os.environ.get("TEST_DB_URL"))

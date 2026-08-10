"""Database engine and session factory.

SQLAlchemy is used with PostgreSQL in production; SQLite is the default local
fallback so the app runs with zero external services. Set DATABASE_URL to a
PostgreSQL connection string to switch engines (no code changes):

    postgresql+psycopg://user:pass@host:5432/network_mapper
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./network_mapper.db")

_connect_args: dict = {}
_poolclass = None
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    if ":memory:" in DATABASE_URL:
        from sqlalchemy.pool import StaticPool

        _poolclass = StaticPool

engine = create_engine(DATABASE_URL, connect_args=_connect_args, poolclass=_poolclass, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def init_db() -> None:
    """Create all tables. Imports models so they register with Base."""
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

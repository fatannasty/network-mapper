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
    _run_migrations()


def _run_migrations() -> None:
    """Lightweight additive migrations for existing databases.

    create_all() only creates missing tables; it never alters existing ones.
    These migrations add new columns/backfills for tables that predate a
    feature so a long-lived dev DB keeps working without a full reset.
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        # Sprint 13: devices.catalyst_id (needed for Catalyst config collection)
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(devices)"))}
        if "catalyst_id" not in cols:
            conn.execute(text("ALTER TABLE devices ADD COLUMN catalyst_id VARCHAR(64) DEFAULT ''"))

        # Sprint 13: scan_jobs.scan_kind (full_env | site:<name> | subnet)
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(scan_jobs)"))}
        if "scan_kind" not in cols:
            conn.execute(text("ALTER TABLE scan_jobs ADD COLUMN scan_kind VARCHAR(64) DEFAULT 'subnet'"))
        # Backfill scan_kind from existing labels. (Column defaults make the
        # value 'subnet' for pre-existing rows, so match on label not NULL.)
        conn.execute(text(
            "UPDATE scan_jobs SET scan_kind='full_env' "
            "WHERE scan_kind='subnet' AND subnet = 'CatC: Full Environment'"
        ))
        conn.execute(text(
            "UPDATE scan_jobs SET scan_kind='site:' || substr(subnet, 7) "
            "WHERE scan_kind='subnet' AND subnet LIKE 'CatC: %'"
        ))

        # Sprint 13: device_configs.collected_by (audit trail — who ran the collection)
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(device_configs)"))}
        if "collected_by" not in cols:
            conn.execute(text("ALTER TABLE device_configs ADD COLUMN collected_by VARCHAR(128)"))

        # Latency: ICMP round-trip time to each device (ping RTT in ms).
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(devices)"))}
        if "latency_ms" not in cols:
            conn.execute(text("ALTER TABLE devices ADD COLUMN latency_ms FLOAT DEFAULT 0.0"))
        if "latency_checked_at" not in cols:
            conn.execute(text("ALTER TABLE devices ADD COLUMN latency_checked_at DATETIME"))

        # Sprint 13: relabel legacy Catalyst topology links from 'unknown' to 'catalyst'.
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(links)"))}
        if "protocol" in cols:
            conn.execute(text(
                "UPDATE links SET protocol='catalyst' WHERE protocol IN ('unknown', '')"
            ))


def get_db():
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

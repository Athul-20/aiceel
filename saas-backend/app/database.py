"""Database engine, session factory and helpers.

All heavy objects (engine, session factory) are created lazily on first
access so that:
  - importing this module has no side-effects
  - tests can override ``DATABASE_URL`` before the engine is created
  - circular-import risks are reduced
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


# ── Modern declarative base ────────────────────────────────

class Base(DeclarativeBase):
    """Base class for all ORM models."""


# ── Lazy engine & session factory ──────────────────────────

@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the global SQLAlchemy engine (created once, cached)."""
    settings = get_settings()
    connect_args = (
        {"check_same_thread": False, "timeout": 30}
        if settings.database_url.startswith("sqlite")
        else {}
    )
    _engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if settings.database_url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA busy_timeout=5000;")
            finally:
                cursor.close()

    return _engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return the global session factory (created once, cached)."""
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


# ── Public helpers (used by routers and deps) ─────────────

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it afterwards."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def db_session_factory() -> Session:
    """Create a standalone session outside of a FastAPI request context."""
    return get_session_factory()()


def ensure_sqlite_compat_schema() -> None:
    """Backfill legacy SQLite databases with required columns for new SaaS features."""
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        return

    _engine = get_engine()

    additions: dict[str, list[str]] = {
        "users": [
            "default_workspace_id INTEGER",
        ],
        "api_keys": [
            "workspace_id INTEGER",
            "scopes_csv TEXT NOT NULL DEFAULT ''",
            "rate_limit_per_minute INTEGER",
            "monthly_quota_units INTEGER",
        ],
        "agent_profiles": [
            "workspace_id INTEGER",
            "provider TEXT NOT NULL DEFAULT 'openai'",
        ],
        "platform_configs": [
            "workspace_id INTEGER",
        ],
        "provider_credentials": [
            "workspace_id INTEGER",
        ],
        "meter_events": [
            "metadata_json TEXT NOT NULL DEFAULT '{}'",
        ],
    }

    with _engine.begin() as conn:
        table_names = set(inspect(conn).get_table_names())
        for table_name, columns in additions.items():
            if table_name not in table_names:
                continue
            existing_columns = {item["name"] for item in inspect(conn).get_columns(table_name)}
            for column_def in columns:
                column_name = column_def.split(" ", 1)[0]
                if column_name in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_def}"))

"""
SQLAlchemy engine/session setup.

Works with Neon Postgres (production) or a local SQLite file (dev fallback).
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


def _normalize_url(url: str) -> str:
    """Neon gives `postgresql://` / `postgres://`; we want the psycopg (v3) driver."""
    url = (url or "").strip().strip("'\"")
    if url.startswith("psql "):
        url = url[len("psql "):].strip().strip("'\"")
    if not url or url.startswith(("http://", "https://")):
        if url.startswith(("http://", "https://")):
            print(
                f"[DB WARNING] DATABASE_URL starts with '{url.split('://')[0]}://' (not a valid Postgres URL). "
                "Falling back to local SQLite until you set DATABASE_URL=postgresql://..."
            )
        return f"sqlite:///{(settings.storage_dir / 'whappend.db').as_posix()}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    # Strip channel_binding=require if present (can hang older libpq builds on Linux containers)
    url = url.replace("&channel_binding=require", "").replace("?channel_binding=require&", "?")
    return url


DATABASE_URL = _normalize_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    # Neon suspends idle compute; pre_ping transparently replaces dead connections.
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"check_same_thread": False} if IS_SQLITE else {"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for non-request code (bot handlers, background jobs, CLI)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables if they don't exist. (Swap for Alembic migrations once the schema stabilizes.)"""
    from db import models  # noqa: F401 — register models

    Base.metadata.create_all(bind=engine)

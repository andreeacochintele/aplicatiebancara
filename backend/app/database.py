"""SQLAlchemy engine/session setup, shared Base and the get_db dependency."""
from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.supabase import SupabaseRestSession

settings = get_settings()

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Python-side default for timestamp columns.

    Deliberately not a DB server_default: it keeps model behavior identical
    across Postgres (production) and SQLite (tests, which has no now())."""
    return datetime.now(timezone.utc)


def get_db() -> Generator[Session | SupabaseRestSession, None, None]:
    if settings.DATABASE_BACKEND == "supabase_rest":
        db = SupabaseRestSession()
        try:
            yield db
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Explicit, rather than relying on Session.close()'s implicit
        # rollback-on-close — makes the abort-on-failure behavior visible
        # here instead of an incidental side effect of cleanup.
        db.rollback()
        raise
    finally:
        db.close()

"""FastAPI dependencies for extracting/validating the current user from a JWT.

Session enforcement (architecture.md §4: 5-minute inactivity logout) lives in
get_current_session — get_current_user layers user-loading on top of it but
keeps its own signature/return type unchanged, since it's depended on by
nearly every router in the app."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import SessionStatus, UserSession
from app.config import get_settings
from app.core.enums import UserRole, UserType
from app.core.security import decode_token
from app.database import get_db
from app.users.models import User
from app.users.repository import UserRepository

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) drops tzinfo on round-trip even for
    DateTime(timezone=True) columns; Postgres preserves it. Normalize so
    comparisons against `datetime.now(timezone.utc)` work on both."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserSession:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    try:
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except (KeyError, ValueError) as exc:
        # Covers tokens issued before the "sid" claim existed too — no legacy
        # fallback: access tokens are dead within 15 minutes regardless.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_session = db.get(UserSession, session_id)
    if user_session is None or user_session.user_id != user_id:
        # Same message for "no such session" and "belongs to someone else" —
        # don't give a caller an oracle to distinguish the two.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session not found")
    if user_session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active")

    now = datetime.now(timezone.utc)
    if _as_aware_utc(user_session.expires_at) <= now:
        user_session.status = SessionStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    idle_cutoff = _as_aware_utc(user_session.last_activity_at) + timedelta(
        minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES
    )
    if now > idle_cutoff:
        user_session.status = SessionStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired due to inactivity")

    # Committed here, independent of whatever the route handler does next:
    # this dependency fully resolves (commit included) before the route body
    # runs, so nothing else is pending on `db` yet. Deferring to the router's
    # own end-of-handler commit would lose this touch whenever the route
    # itself later raises a DomainError (e.g. a failed validation) — an
    # active user would then be wrongly logged out for "inactivity".
    user_session.last_activity_at = now
    db.commit()
    return user_session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    user = UserRepository(db).get_by_id(session.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user


def require_business(current_user: User = Depends(get_current_user)) -> User:
    if current_user.user_type != UserType.BUSINESS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business account required")
    return current_user

"""Login/register/session business logic. Session tracking backs the 5-minute
inactivity auto-logout described in architecture.md §4 (enforcement of the
timeout itself happens in `dependencies.get_current_user`)."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import SessionStatus, UserDevice, UserSession
from app.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.supabase import is_supabase_session
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import UserCreate
from app.users.service import UserService

settings = get_settings()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) drops tzinfo on round-trip even for
    DateTime(timezone=True) columns; Postgres preserves it. Normalize so
    comparisons against `datetime.now(timezone.utc)` work on both."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def register(self, data: UserCreate) -> User:
        return UserService(self.db).create_user(data)

    def authenticate(self, email: str, password: str) -> User:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        user.last_login_at = datetime.now(timezone.utc)
        return user

    def issue_tokens(self, user: User, device_id: uuid.UUID | None = None) -> tuple[str, str]:
        if device_id is None:
            device_id = self._get_or_create_default_device(user).id

        # Generated up front (UserSession.id has only a Python-side default,
        # applied at flush) so both tokens can embed the same "sid" claim as
        # the session row they belong to, with no insert-then-reissue step.
        session_id = uuid.uuid4()
        access_token = create_access_token(str(user.id), str(session_id))
        refresh_token = create_refresh_token(str(user.id), str(session_id))

        session = UserSession(
            id=session_id,
            user_id=user.id,
            device_id=device_id,
            token_hash=_hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            status=SessionStatus.ACTIVE,
        )
        self.db.add(session)
        self.db.flush()
        return access_token, refresh_token

    def refresh_access_token(self, refresh_token: str) -> str:
        """Mint a new access token for a still-valid session. Deliberately does
        NOT touch last_activity_at: this call is driven by the frontend's
        background timer, not a real user action, so it must not itself
        reset the 5-minute inactivity window (see get_current_session) —
        otherwise a genuinely idle tab would stay "active" forever."""
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired refresh token") from exc
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")
        try:
            user_id = uuid.UUID(payload["sub"])
            session_id = uuid.UUID(payload["sid"])
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("Invalid token") from exc

        session = self.db.get(UserSession, session_id)
        if session is None or session.user_id != user_id or session.token_hash != _hash_token(refresh_token):
            raise AuthenticationError("Session not found")
        if session.status != SessionStatus.ACTIVE:
            raise AuthenticationError("Session is no longer active")

        now = datetime.now(timezone.utc)
        if _as_aware_utc(session.expires_at) <= now:
            session.status = SessionStatus.EXPIRED
            self.db.commit()
            raise AuthenticationError("Session expired")

        idle_cutoff = _as_aware_utc(session.last_activity_at) + timedelta(
            minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES
        )
        if now > idle_cutoff:
            session.status = SessionStatus.EXPIRED
            self.db.commit()
            raise AuthenticationError("Session expired due to inactivity")

        return create_access_token(str(user_id), str(session_id))

    def _get_or_create_default_device(self, user: User) -> UserDevice:
        # A device is only genuinely "new" the first time it's ever seen —
        # every login after that reuses this same placeholder row (there's
        # no real per-browser fingerprinting here), so once we've seen it
        # again it's a returning session, not a new one. Without this,
        # trusted stayed False forever (nothing else in the app ever sets
        # it True) and the fraud engine's NEW_DEVICE flag fired on every
        # single card payment for every user.
        now = datetime.now(timezone.utc)
        if is_supabase_session(self.db):
            devices = self.db.fetch_many(
                UserDevice,
                {"user_id": f"eq.{user.id}", "order": "last_seen_at.desc", "limit": "1"},
            )
            if devices:
                device = devices[0]
                device.last_seen_at = now
                device.trusted = True
                self.db.flush()
                return device
        else:
            device = self.db.scalar(
                select(UserDevice)
                .where(UserDevice.user_id == user.id)
                .order_by(UserDevice.last_seen_at.desc())
                .limit(1)
            )
            if device is not None:
                device.last_seen_at = now
                device.trusted = True
                self.db.flush()
                return device

        device = UserDevice(
            user_id=user.id,
            device_name="Web browser",
            device_type="browser",
            browser="Unknown",
            operating_system="Unknown",
            trusted=False,
        )
        self.db.add(device)
        self.db.flush()
        return device

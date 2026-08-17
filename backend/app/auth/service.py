"""Login/register/session business logic. Session tracking backs the 5-minute
inactivity auto-logout described in architecture.md §4 (enforcement of the
timeout itself happens in `dependencies.get_current_user`)."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.models import SessionStatus, UserSession
from app.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import UserCreate
from app.users.service import UserService

settings = get_settings()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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
        access_token = create_access_token(str(user.id))
        refresh_token = create_refresh_token(str(user.id))

        session = UserSession(
            user_id=user.id,
            device_id=device_id,
            token_hash=_hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            status=SessionStatus.ACTIVE,
        )
        self.db.add(session)
        self.db.flush()
        return access_token, refresh_token

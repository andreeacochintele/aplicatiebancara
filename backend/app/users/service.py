"""Business logic for user creation. Enforces uniqueness of email/phone."""
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.notifications.service import NotificationsService
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import UserCreate


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = UserRepository(db)
        self.notifications = NotificationsService(db)

    def create_user(self, data: UserCreate) -> User:
        if self.repository.get_by_email(data.email):
            raise ConflictError(f"Email '{data.email}' is already registered")
        if data.phone and self.repository.get_by_phone(data.phone):
            raise ConflictError(f"Phone '{data.phone}' is already registered")

        user = User(
            email=data.email,
            phone=data.phone,
            password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            user_type=data.user_type,
        )
        user = self.repository.add(user)

        # Best-effort: a notification failure must never make registration
        # itself look like it failed.
        try:
            self.notifications.create(
                user.id,
                type="SYSTEM",
                title="Welcome to Aurora",
                message=f"Hi {user.first_name}, your account is ready. Set up your first wallet to get started.",
            )
        except Exception:
            pass
        return user

"""Data-access layer for User. No business rules here, only queries."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.users.models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def get_by_phone(self, phone: str) -> User | None:
        return self.db.scalar(select(User).where(User.phone == phone))

    def list_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        return list(self.db.scalars(select(User).limit(limit).offset(offset)))

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

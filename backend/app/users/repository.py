"""Data-access layer for User. No business rules here, only queries."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.users.models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        if is_supabase_session(self.db):
            return self.db.get(User, user_id)
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(User, {"email": f"eq.{email}"})
        return self.db.scalar(select(User).where(User.email == email))

    def get_by_phone(self, phone: str) -> User | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(User, {"phone": f"eq.{phone}"})
        return self.db.scalar(select(User).where(User.phone == phone))

    def list_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(User, {"limit": str(limit), "offset": str(offset)})
        return list(self.db.scalars(select(User).limit(limit).offset(offset)))

    def add(self, user: User) -> User:
        if is_supabase_session(self.db):
            return self.db.add(user)
        self.db.add(user)
        self.db.flush()
        return user

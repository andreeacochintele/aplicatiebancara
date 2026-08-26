"""Registration, login, and session endpoints."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_session
from app.auth.models import SessionStatus, UserSession
from app.auth.schemas import AuthResponse, LoginRequest, RegisterRequest, TokenResponse
from app.auth.service import AuthService
from app.database import get_db
from app.users.schemas import UserCreate, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    service = AuthService(db)
    user = service.register(UserCreate(**payload.model_dump()))
    access_token, refresh_token = service.issue_tokens(user)
    db.commit()
    return AuthResponse(
        user=UserPublic.model_validate(user),
        tokens=TokenResponse(access_token=access_token, refresh_token=refresh_token),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> Response:
    session.status = SessionStatus.REVOKED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    service = AuthService(db)
    user = service.authenticate(payload.email, payload.password)
    access_token, refresh_token = service.issue_tokens(user)
    db.commit()
    return AuthResponse(
        user=UserPublic.model_validate(user),
        tokens=TokenResponse(access_token=access_token, refresh_token=refresh_token),
    )

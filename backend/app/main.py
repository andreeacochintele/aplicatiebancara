"""FastAPI application entrypoint."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api_v1 import api_router
from app.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

settings = get_settings()

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DOMAIN_ERROR_STATUS = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
    AuthenticationError: 401,
    AuthorizationError: 403,
}


@app.exception_handler(DomainError)
def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    status_code = next((code for cls, code in _DOMAIN_ERROR_STATUS.items() if isinstance(exc, cls)), 400)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get(f"{settings.API_V1_PREFIX}/health", tags=["health"])
def health_v1() -> dict:
    return {"status": "ok"}

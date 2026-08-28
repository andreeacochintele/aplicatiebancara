"""Domain-level exceptions. Routers translate these into HTTP responses."""


class DomainError(Exception):
    """Base class for all business-rule violations raised from services."""


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class AuthenticationError(DomainError):
    pass


class AuthorizationError(DomainError):
    pass


def is_unique_violation(exc: Exception) -> bool:
    """True for a UNIQUE-constraint violation from either DB backend this
    app supports — SQLAlchemy's IntegrityError (Postgres/SQLite), or the
    Supabase REST shim's RuntimeError (PostgREST passes through Postgres's
    own SQLSTATE; 23505 is unique_violation). Use this to turn a
    check-then-insert race (the check passed, but a concurrent request beat
    this one to the insert) into a clean ConflictError instead of a bare 500."""
    from sqlalchemy.exc import IntegrityError

    if isinstance(exc, IntegrityError):
        return True
    return isinstance(exc, RuntimeError) and "23505" in str(exc)

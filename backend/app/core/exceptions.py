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

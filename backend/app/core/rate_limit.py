"""In-memory, per-process rate limiting for sensitive endpoints (login,
register) — nothing in this app currently stops a brute-force attempt
against either. No Redis/queue infrastructure exists anywhere in this
codebase, so this is a fixed-window counter keyed by client IP, module-level
like fx/service.py's live-rate cache — same known limitation (per-process
only, resets on restart, doesn't share state across multiple app instances),
acceptable for the same reason that one is: this app runs as a single
process, not horizontally scaled.

Tests override each limiter instance to a no-op via
app.dependency_overrides (see tests/conftest.py) so the hundreds of
register/login calls across the suite don't trip it — see
tests/test_rate_limit.py for the dedicated test that exercises the real
limiting behavior.
"""
import threading
import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import HTTPException, Request, status

_lock = threading.Lock()
_hits: dict[str, list[float]] = defaultdict(list)


def rate_limiter(key_prefix: str, max_attempts: int, window_seconds: int) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{key_prefix}:{client_ip}"
        now = time.monotonic()
        cutoff = now - window_seconds
        with _lock:
            hits = _hits[key]
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= max_attempts:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts — try again in a few minutes.",
                )
            hits.append(now)

    return dependency


def reset_rate_limits() -> None:
    """Test-only: clears all recorded hits so tests don't leak state into
    each other when a test deliberately re-enables a limiter."""
    with _lock:
        _hits.clear()

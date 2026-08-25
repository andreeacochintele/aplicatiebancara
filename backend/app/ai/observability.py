"""Structured, human-readable logging for the AI orchestration flow.

Scope: ai/orchestrator/, the three orchestrator-registered agents, and
ai/fraud/'s Fraud Investigation Agent (admin-triggered, not orchestrator-
registered, but reuses this same module rather than inventing its own
logging — see ai/fraud/agent.py). Not used outside ai/.

One correlation_id per chat/investigation request, generated in
ai/orchestrator/service.py (or ai/fraud/agent.py's investigate()) and
carried via a `contextvars.ContextVar` rather than threaded as an explicit
parameter through every function signature. That keeps `ai/orchestrator/registry.py`'s `AgentHandler`
contract and every tool function's signature unchanged, so nothing that
calls them — including existing tests — needs to change. Each request
runs in its own copied context (FastAPI's `run_in_threadpool` copies the
context per call), so concurrent requests never see each other's
correlation_id.

Log lines use Python's standard `logging` module with `extra={}` fields
(structured, filterable) rendered by `_ReadableFormatter` into a single
grep-friendly line, not a JSON blob:

    [a1b2c3d4] event=tool_call tool=get_wallet_balances duration_ms=4.2 status=ok

`watch a live conversation`: `docker compose logs backend -f | grep a1b2c3d4`
(PowerShell: `... | Select-String a1b2c3d4`) — see ai/README.md.

Everything above is logged at INFO. Full LLM prompt/response bodies are
logged separately at DEBUG (see each agent's `_explain()`) since they're
verbose and not needed for normal manual QA — turn `LOG_LEVEL=DEBUG` on
only when you need to see raw model output.

Every llm_call event also carries prompt_tokens/completion_tokens,
confirmed live to be populated by this Azure Foundry endpoint. See
`record_usage()` and `_last_usage` below for how token counts reach this
module from ai/client/azure_foundry_client.py without any agent's own
code (personal_finance, credit, support, or the orchestrator's intent
classifier) needing to extract or pass them.
"""
import functools
import inspect
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, TypeVar

logger = logging.getLogger("app.ai")
logger.setLevel(os.environ.get("AI_LOG_LEVEL", "INFO").upper())
logger.propagate = False  # dedicated handler below; don't also go through root/uvicorn's formatting

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)

    class _ReadableFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            correlation_id = getattr(record, "correlation_id", "-")
            event = getattr(record, "event", record.getMessage())
            fields = getattr(record, "fields", {})
            rendered = " ".join(f"{key}={value}" for key, value in fields.items())
            line = f"[{correlation_id}] event={event}"
            return f"{line} {rendered}" if rendered else line

    _handler.setFormatter(_ReadableFormatter())
    logger.addHandler(_handler)

_correlation_id: ContextVar[str] = ContextVar("ai_correlation_id", default="-")

# Token usage for the llm_call event. Set by
# ai/client/azure_foundry_client.py's chat_completion() right after every
# response, read (and cleared) by timed_event()'s own exit. This is the one
# non-self-contained piece of this module: a `with timed_event("llm_call",
# ...): response = client.chat_completion(...)` block is a Python context
# manager wrapping arbitrary code, so it has no way to see `response` — a
# local variable created inside its own body — without the call inside that
# body reporting it back somehow. Every llm_call call site (orchestrator's
# classify_intent, and every agent's response-generation call, including
# ai/credit/'s) already follows exactly that one-call-per-block shape, so
# routing it through the shared client this way gets token counts onto
# every llm_call log line without editing any of those call sites.
_last_usage: ContextVar[Any | None] = ContextVar("ai_last_usage", default=None)

F = TypeVar("F", bound=Callable[..., Any])


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:8]


def record_usage(usage: Any | None) -> None:
    """Called by azure_foundry_client.py's chat_completion() with the SDK
    response's `.usage` (or None if the response didn't have one) — see
    `_last_usage`'s comment above for why this exists."""
    _last_usage.set(usage)


def _consume_usage_fields() -> dict[str, Any]:
    usage = _last_usage.get()
    _last_usage.set(None)  # consumed once so a stale value can't leak into a later event
    if usage is None:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def bind_correlation_id(correlation_id: str) -> None:
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str:
    return _correlation_id.get()


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, event, extra={"correlation_id": get_correlation_id(), "event": event, "fields": fields})


def log_debug(event: str, **fields: Any) -> None:
    log_event(event, level=logging.DEBUG, **fields)


@contextmanager
def timed_event(event: str, **fields: Any) -> Iterator[None]:
    """Logs `event` once the wrapped block finishes: duration_ms and
    status=ok, or status=error + error_type on an exception (re-raised
    unchanged — this never swallows or alters what the caller sees). For
    event="llm_call", also attaches prompt_tokens/completion_tokens if a
    chat_completion() call happened inside the block (see
    record_usage()) — any stale value from a previous block is cleared
    before this one starts, so token counts always belong to the actual
    call this specific block wraps, never a leftover from elsewhere."""
    _last_usage.set(None)
    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        log_event(event, duration_ms=duration_ms, status="error", error_type=type(exc).__name__, **fields)
        raise
    else:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        usage_fields = _consume_usage_fields() if event == "llm_call" else {}
        log_event(event, duration_ms=duration_ms, status="ok", **fields, **usage_fields)


def log_tool_call(func: F) -> F:
    """Decorator for a tools.py function: logs event=tool_call with the
    tool's name, its call arguments (everything except `ctx`/`db` — a
    ToolContext or raw Session isn't a meaningful thing to render, and
    correlation_id already ties the line back to the request/user), how
    long it took, and success/failure. Apply directly to each tool function
    definition so tools.py's own call sites (and agent.py's dispatch) stay
    unchanged."""
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        loggable_args = {name: value for name, value in bound.arguments.items() if name not in ("ctx", "db")}
        with timed_event("tool_call", tool=func.__name__, **loggable_args):
            return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]

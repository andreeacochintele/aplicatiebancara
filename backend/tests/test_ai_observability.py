import logging
from types import SimpleNamespace

import pytest

from app.ai import observability
from app.ai.observability import (
    bind_correlation_id,
    get_correlation_id,
    log_event,
    log_tool_call,
    new_correlation_id,
    record_usage,
    timed_event,
)
from app.ai.tools.base import ToolContext


def test_new_correlation_id_is_short_and_unique():
    a, b = new_correlation_id(), new_correlation_id()
    assert a != b
    assert 1 <= len(a) <= 12


def test_bind_and_get_correlation_id_round_trip():
    bind_correlation_id("abc123")
    assert get_correlation_id() == "abc123"


def test_readable_formatter_renders_a_single_grep_friendly_line():
    formatter = observability._ReadableFormatter()
    record = logging.LogRecord(
        name="app.ai", level=logging.INFO, pathname=__file__, lineno=1, msg="tool_call", args=(), exc_info=None
    )
    record.correlation_id = "a1b2c3d4"
    record.event = "tool_call"
    record.fields = {"tool": "get_wallet_balances", "duration_ms": 4.2, "status": "ok"}

    line = formatter.format(record)

    assert line == "[a1b2c3d4] event=tool_call tool=get_wallet_balances duration_ms=4.2 status=ok"


def test_readable_formatter_handles_no_extra_fields():
    formatter = observability._ReadableFormatter()
    record = logging.LogRecord(
        name="app.ai", level=logging.INFO, pathname=__file__, lineno=1, msg="request_received", args=(), exc_info=None
    )
    record.correlation_id = "a1b2c3d4"
    record.event = "request_received"
    record.fields = {}

    assert formatter.format(record) == "[a1b2c3d4] event=request_received"


def test_log_event_attaches_the_bound_correlation_id(caplog):
    bind_correlation_id("xyz789")
    with caplog.at_level(logging.INFO, logger="app.ai"):
        log_event("some_event", foo="bar")

    record = caplog.records[-1]
    assert record.correlation_id == "xyz789"
    assert record.event == "some_event"
    assert record.fields == {"foo": "bar"}


def test_timed_event_logs_ok_status_and_a_duration_on_success(caplog):
    bind_correlation_id("t1")
    with caplog.at_level(logging.INFO, logger="app.ai"):
        with timed_event("llm_call", agent="support"):
            pass

    record = caplog.records[-1]
    assert record.fields["status"] == "ok"
    assert record.fields["agent"] == "support"
    assert isinstance(record.fields["duration_ms"], float)
    assert "error_type" not in record.fields


def test_timed_event_logs_error_status_and_reraises(caplog):
    bind_correlation_id("t2")
    with caplog.at_level(logging.INFO, logger="app.ai"):
        with pytest.raises(ValueError):
            with timed_event("tool_call", tool="whatever"):
                raise ValueError("boom")

    record = caplog.records[-1]
    assert record.fields["status"] == "error"
    assert record.fields["error_type"] == "ValueError"


def test_log_tool_call_logs_arguments_by_name_and_excludes_ctx(caplog, db_session):
    @log_tool_call
    def a_tool(ctx: ToolContext, extra_payment_amount) -> str:
        return "ok"

    bind_correlation_id("t3")
    ctx = ToolContext(user_id=__import__("uuid").uuid4(), db=db_session)
    with caplog.at_level(logging.INFO, logger="app.ai"):
        result = a_tool(ctx, 500)

    assert result == "ok"
    record = caplog.records[-1]
    assert record.event == "tool_call"
    assert record.fields["tool"] == "a_tool"
    assert record.fields["extra_payment_amount"] == 500
    assert "ctx" not in record.fields


def test_log_tool_call_preserves_the_wrapped_function_name_and_docstring():
    @log_tool_call
    def a_documented_tool(ctx: ToolContext) -> None:
        """A docstring."""

    assert a_documented_tool.__name__ == "a_documented_tool"
    assert a_documented_tool.__doc__ == "A docstring."


# ---- token usage: reported via record_usage() (called by
# azure_foundry_client.py, not asserted here — see test_ai_client.py),
# consumed by timed_event()'s own "llm_call" success path ----


def test_timed_event_llm_call_attaches_token_usage_when_recorded(caplog):
    bind_correlation_id("u1")
    usage = SimpleNamespace(prompt_tokens=23, completion_tokens=141)
    with caplog.at_level(logging.INFO, logger="app.ai"):
        with timed_event("llm_call", agent="credit"):
            record_usage(usage)

    record = caplog.records[-1]
    assert record.fields["prompt_tokens"] == 23
    assert record.fields["completion_tokens"] == 141
    # unrelated existing fields are untouched
    assert record.fields["status"] == "ok"
    assert record.fields["agent"] == "credit"


def test_timed_event_llm_call_without_a_recorded_usage_omits_token_fields(caplog):
    bind_correlation_id("u2")
    with caplog.at_level(logging.INFO, logger="app.ai"):
        with timed_event("llm_call", agent="support"):
            pass

    record = caplog.records[-1]
    assert "prompt_tokens" not in record.fields
    assert "completion_tokens" not in record.fields


def test_timed_event_non_llm_call_events_never_get_token_fields_even_if_usage_was_recorded(caplog):
    bind_correlation_id("u3")
    record_usage(SimpleNamespace(prompt_tokens=1, completion_tokens=2))
    with caplog.at_level(logging.INFO, logger="app.ai"):
        with timed_event("tool_call", tool="get_credit_score"):
            pass

    record = caplog.records[-1]
    assert "prompt_tokens" not in record.fields
    assert "completion_tokens" not in record.fields


def test_timed_event_clears_stale_usage_from_an_earlier_block(caplog):
    bind_correlation_id("u4")
    with timed_event("llm_call", agent="credit"):
        record_usage(SimpleNamespace(prompt_tokens=99, completion_tokens=99))
    # A second, unrelated llm_call block that never records its own usage
    # must not inherit the first block's leftover value.
    with caplog.at_level(logging.INFO, logger="app.ai"):
        with timed_event("llm_call", agent="support"):
            pass

    record = caplog.records[-1]
    assert "prompt_tokens" not in record.fields
    assert "completion_tokens" not in record.fields

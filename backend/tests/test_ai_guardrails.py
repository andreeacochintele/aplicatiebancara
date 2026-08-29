from app.ai.guardrails import _FALLBACK_MESSAGE, ensure_plain_text


def test_ensure_plain_text_passes_through_normal_prose():
    reply = "Your Gold card earns points about 1.5x faster than Regular."
    assert ensure_plain_text(reply) == reply


def test_ensure_plain_text_passes_through_empty_string():
    assert ensure_plain_text("") == ""


def test_ensure_plain_text_replaces_a_raw_json_object():
    reply = '{"risk_level": "HIGH", "explanation": "..."}'
    assert ensure_plain_text(reply) == _FALLBACK_MESSAGE


def test_ensure_plain_text_replaces_a_raw_json_array():
    reply = '["one", "two", "three"]'
    assert ensure_plain_text(reply) == _FALLBACK_MESSAGE


def test_ensure_plain_text_replaces_json_wrapped_in_a_code_fence():
    reply = '```json\n{"balance": 100}\n```'
    assert ensure_plain_text(reply) == _FALLBACK_MESSAGE


def test_ensure_plain_text_unwraps_plain_prose_from_a_code_fence():
    reply = "```\nYour balance is 100 RON.\n```"
    assert ensure_plain_text(reply) == "Your balance is 100 RON."


def test_ensure_plain_text_does_not_flag_an_inline_code_span_inside_prose():
    reply = "Your balance is `100 RON`, right on target."
    assert ensure_plain_text(reply) == reply


def test_ensure_plain_text_does_not_flag_text_that_merely_mentions_braces():
    reply = "In math, {1, 2, 3} is a set — not something I can help with here."
    assert ensure_plain_text(reply) == reply

"""Follow-up question suggestions — one cheap GPT-5-mini call right after a
personal_finance/credit/support reply, so the UI can offer 2-3 clickable
"ask next" chips. Triggered from OrchestratorService.chat(), skipped
entirely for greeting/out_of_scope (see that method — not worth the extra
call there, those replies are fixed strings with no LLM call of their
own). Best-effort: a failed/unconfigured call returns an empty list rather
than raising — a missing suggestion list must never break the chat reply
that's already been computed and persisted, same principle as title.py.
"""
import re

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.observability import timed_event

# Strips a leading "1. ", "2) ", "- ", "• " etc. in case the model doesn't
# follow the "no numbering" instruction exactly — same defensive spirit as
# title.py's _clean_title().
_LEADING_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s*")

_SYSTEM_PROMPT = (
    "Given this exchange, suggest 2-3 short natural follow-up questions the "
    "user might ask next, in the same language as the conversation. Return "
    "ONLY the questions, one per line, no numbering."
)

_MAX_FOLLOWUPS = 3


def generate_followup_questions(user_message: str, reply: str) -> list[str]:
    """One cheap call through the shared client, same pattern as
    title.py/intent.py — reasoning_effort="minimal" since suggesting a
    couple of plausible next questions needs no deep reasoning."""
    client = get_azure_foundry_client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"User: {user_message}\nAssistant: {reply}"},
    ]
    with timed_event("llm_call", agent="orchestrator_followups"):
        response = client.chat_completion(messages=messages, reasoning_effort="minimal")
    return _parse_followups(response.choices[0].message.content)


def _parse_followups(raw: str) -> list[str]:
    """One question per line, with a leading numbering/bullet marker
    stripped defensively (see _LEADING_MARKER above). Capped at
    _MAX_FOLLOWUPS even if the model returns more than asked."""
    questions = [_LEADING_MARKER.sub("", line).strip() for line in raw.splitlines()]
    return [q for q in questions if q][:_MAX_FOLLOWUPS]

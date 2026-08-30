"""Follow-up reply-chip suggestions — one cheap GPT-5-mini call right after a
personal_finance/credit/support reply, so the UI can offer 2-3 clickable
chips. A chip's text is sent verbatim as the user's own next message when
tapped, so every chip must read as something the user would say, never a
question mirrored back from the agent's own reply (see _SYSTEM_PROMPT).
Triggered from OrchestratorService.chat(), skipped entirely for
greeting/out_of_scope (see that method — not worth the extra call there,
those replies are fixed strings with no LLM call of their own). Best-effort:
a failed/unconfigured call returns an empty list rather than raising — a
missing suggestion list must never break the chat reply that's already been
computed and persisted, same principle as title.py.
"""
import re

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.observability import timed_event

# Strips a leading "1. ", "2) ", "- ", "• " etc. in case the model doesn't
# follow the "no numbering" instruction exactly — same defensive spirit as
# title.py's _clean_title().
_LEADING_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s*")

_SYSTEM_PROMPT = (
    "Given this exchange, suggest 2-3 short clickable chips for the user's "
    "chat UI. CRITICAL: when tapped, a chip's exact text is sent as the "
    "USER's own next message — so every chip must be phrased as something "
    "the user would say TO the assistant: a first-person statement, "
    "request, or answer. NEVER phrase a chip as a question directed at the "
    "user, and NEVER phrase a chip as a question mirrored or restated from "
    "the Assistant's own reply above — that would make the user appear to "
    "ask themselves the assistant's own question.\n"
    "If the Assistant's reply above asks the user to choose between "
    "specific options (e.g. 'Care vrei: soldul actual, ultimele 10 "
    "tranzacții sau detaliile cardului?'), generate one chip per option, "
    "each phrased as the user picking it — e.g. 'Soldul actual', "
    "'Ultimele 10 tranzacții', 'Detaliile cardului' — never one chip that "
    "just repeats the Assistant's question back.\n"
    "If the Assistant's reply asks for a single open piece of information "
    "(an amount, a date, etc.) that can't be guessed, do not create a chip "
    "that repeats or closely rephrases that same open question — suggest "
    "other genuinely useful next actions instead.\n"
    "If the Assistant's reply already fully answered the user with no "
    "question pending, suggest short, unambiguous requests for one "
    "specific thing the user might want next (a specific figure, category, "
    "time period, or action) — never a vague or generic prompt like 'tell "
    "me more'.\n"
    "CRITICAL: write every chip in the SAME language as the Assistant's "
    "reply above — if the reply is in English, all chips must be in "
    "English; if the reply is in Romanian, all chips must be in Romanian. "
    "Judge the language from the Assistant's reply, not the user's "
    "message, in case the two differ. Return ONLY the chip texts, one per "
    "line, no numbering."
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

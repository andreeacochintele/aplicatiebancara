"""Intent classification for the Orchestrator Agent.

Classifies a user message into one of five categories via the shared Azure
GPT-5-mini client (never a separate/local classifier). `personal_finance`,
`credit`, and `support` route to a specialized agent (see registry.py);
`greeting` and `out_of_scope` are answered directly by the orchestrator
(see service.py) and never reach an agent. Fraud is intentionally absent —
the Fraud Investigation Agent is out of scope for this orchestrator.
"""
from enum import Enum

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.observability import log_debug, log_event, timed_event

_SYSTEM_PROMPT = (
    "You are the intent classifier for a banking assistant. Classify ONLY the "
    "user's most recent message into exactly one of these categories:\n"
    "- personal_finance: spending, budgets, savings goals, cash flow, cashback\n"
    "- credit: credit score, loans, eligibility, repayment\n"
    "- support: account/app help that isn't personal_finance or credit\n"
    "- greeting: a greeting or small talk with no banking request\n"
    "- out_of_scope: anything unrelated to banking (general knowledge, code, "
    "other unrelated tasks)\n"
    "Conversation history, if shown below, is ONLY there to help you resolve "
    "ambiguous references in the current message (e.g. 'that', 'it', 'the same "
    "period'). It is NOT a hint to reuse whichever category was used last — if "
    "the current message is about a different topic than earlier turns, "
    "classify it under that new topic even though a different category was "
    "used moments ago.\n"
    "Reply with only the category name, nothing else."
)


class IntentCategory(str, Enum):
    PERSONAL_FINANCE = "personal_finance"
    CREDIT = "credit"
    SUPPORT = "support"
    GREETING = "greeting"
    OUT_OF_SCOPE = "out_of_scope"


def classify_intent(message: str, history: list[dict[str, str]] | None = None) -> IntentCategory:
    """Classify `message` using the shared Azure GPT-5-mini client.

    `history` (oldest first, role/content dicts — see service.py's
    HISTORY_LIMIT) is prior conversation turns shown as context only. The
    classification is always re-evaluated fresh from `message` — see the
    system prompt above; this function has no memory of its own and never
    special-cases "same as last time" based on history.

    Raises `AzureFoundryNotConfiguredError` (from
    app.ai.client.azure_foundry_client) if Azure AI Foundry credentials are
    not set — callers decide how to surface that (see router.py, which
    turns it into a 503).
    """
    client = get_azure_foundry_client()
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}, *(history or []), {"role": "user", "content": message}]
    log_debug("llm_call.request", agent="orchestrator", messages=messages)
    # No temperature override: this GPT-5-mini deployment is a reasoning
    # model that only accepts the default (1) — confirmed live, see
    # azure_foundry_client.py's module docstring.
    with timed_event("llm_call", agent="orchestrator"):
        response = client.chat_completion(messages=messages)
    raw = response.choices[0].message.content.strip().lower()
    log_debug("llm_call.response", agent="orchestrator", content=raw)

    category = _parse_category(raw)
    log_event("intent_classified", intent=category.value, confidence="n/a")
    return category


def _parse_category(raw: str) -> IntentCategory:
    for category in IntentCategory:
        if category.value in raw:
            return category
    return IntentCategory.OUT_OF_SCOPE

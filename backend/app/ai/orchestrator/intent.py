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

_SYSTEM_PROMPT = (
    "You are the intent classifier for a banking assistant. Classify the "
    "user's message into exactly one of these categories:\n"
    "- personal_finance: spending, budgets, savings goals, cash flow, cashback\n"
    "- credit: credit score, loans, eligibility, repayment\n"
    "- support: account/app help that isn't personal_finance or credit\n"
    "- greeting: a greeting or small talk with no banking request\n"
    "- out_of_scope: anything unrelated to banking (general knowledge, code, "
    "other unrelated tasks)\n"
    "Reply with only the category name, nothing else."
)


class IntentCategory(str, Enum):
    PERSONAL_FINANCE = "personal_finance"
    CREDIT = "credit"
    SUPPORT = "support"
    GREETING = "greeting"
    OUT_OF_SCOPE = "out_of_scope"


def classify_intent(message: str) -> IntentCategory:
    """Classify `message` using the shared Azure GPT-5-mini client.

    Raises `AzureFoundryNotConfiguredError` (from
    app.ai.client.azure_foundry_client) if Azure AI Foundry credentials are
    not set — callers decide how to surface that (see router.py, which
    turns it into a 503).
    """
    client = get_azure_foundry_client()
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip().lower()
    return _parse_category(raw)


def _parse_category(raw: str) -> IntentCategory:
    for category in IntentCategory:
        if category.value in raw:
            return category
    return IntentCategory.OUT_OF_SCOPE

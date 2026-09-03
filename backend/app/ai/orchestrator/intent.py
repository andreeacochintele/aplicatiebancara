"""Intent classification for the Orchestrator Agent.

Classifies a user message into one of six categories via the shared Azure
GPT-5-mini client (never a separate/local classifier). `personal_finance`,
`credit`, `support`, and `action` route to a specialized agent (see
registry.py); `greeting` and `out_of_scope` are answered directly by the
orchestrator (see service.py) and never reach an agent. Fraud is
intentionally absent — the Fraud Investigation Agent is out of scope for
this orchestrator.
"""
from enum import Enum

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.observability import log_debug, log_event, timed_event

_SYSTEM_PROMPT = (
    "You are the intent classifier for a banking assistant. Classify ONLY the "
    "user's most recent message into exactly one of these categories:\n"
    "- personal_finance: spending, budgets, savings goals, cash flow, cashback\n"
    "- credit: credit score, loans, eligibility, repayment questions or simulations\n"
    "- support: account/app help that isn't personal_finance or credit\n"
    "- action: the user wants to DO a banking action right now — send money "
    "or make a transfer to a named person, pay a loan installment, make an "
    "early loan repayment, or repay a credit card balance (e.g. 'trimite 100 "
    "lei lui Alex', 'send 50 RON to Maria', 'pay my loan installment', "
    "'ramburseaza 500 RON la credit', 'pay my credit card'). NOT a how-to "
    "question about transfers or repayments.\n"
    "- greeting: a greeting or small talk with no banking request\n"
    "- out_of_scope: anything unrelated to banking (general knowledge, code, "
    "other unrelated tasks)\n"
    "\n"
    "personal_finance vs support is the trickiest distinction: personal_finance "
    "is for the user's OWN real numbers/data (their balance, their spending, "
    "their budget status, their savings progress, their transactions, their "
    "cashback). support is for understanding HOW a feature works, general "
    "app/account questions, or fraud-awareness questions — even if the "
    "question mentions a personal_finance-sounding word like 'budget', "
    "'balance', or 'cashback'. If the question asks for the user's actual "
    "current data/numbers, classify personal_finance. If it asks how "
    "something works, what a feature does, or is a general/conceptual "
    "question, classify support — even if it mentions financial terms.\n"
    "\n"
    "personal_finance vs credit is the other common mix-up: even though both "
    "can be about the user's own real data, anything about a LOAN or CREDIT "
    "SCORE specifically — the user's own loan details, monthly loan payment, "
    "remaining loan principal, loan applications, or early repayment — is "
    "credit, not personal_finance, even when it's phrased just like a "
    "personal_finance question ('my payment', 'my loans', 'how much do I "
    "owe'). personal_finance's 'own data' territory is wallet balance, "
    "spending, budgets, savings goals, transactions, and cashback — it does "
    "NOT include loans or credit score, no matter how the question is phrased.\n"
    "\n"
    "Examples:\n"
    "'What is my wallet balance?' -> personal_finance (asking for their own real figure)\n"
    "'How do budgets work in this app?' -> support (asking how the feature works, not for their own data)\n"
    "'How does savings work?' -> support\n"
    "'How much do I have saved?' -> personal_finance\n"
    "'What's a cashback offer?' -> support\n"
    "'Do I have any cashback right now?' -> personal_finance\n"
    "'What counts as a transaction?' -> support\n"
    "'Show me my recent transactions' -> personal_finance\n"
    "'What is a fraud score and how is it calculated?' -> support (asking how "
    "fraud scoring works conceptually, not a credit score/loan question)\n"
    "'Can I get an account statement?' -> personal_finance (a real export of "
    "their own account activity, not a question about how statements work)\n"
    "'Tell me about my loans' -> credit (their own data, but loans are credit's territory, not personal_finance's)\n"
    "'What's my monthly payment?' -> credit (a loan repayment figure)\n"
    "'How much do I still owe?' -> credit (remaining loan principal)\n"
    "'Do I have any pending loan applications?' -> credit\n"
    "'Can I pay off my loan early?' -> credit (early repayment)\n"
    "'Pay my loan installment' -> action\n"
    "'Make a 500 RON early repayment on my loan' -> action\n"
    "'Plateste rata la credit' -> action\n"
    "'Ramburseaza 500 RON la creditul meu' -> action\n"
    "'Pay my credit card balance' -> action\n"
    "\n"
    "Users may write in Romanian as well as English — classify by meaning, "
    "not by language. The same personal_finance-vs-support distinction "
    "applies regardless of which language the message is in:\n"
    "'Ce sold am?' -> personal_finance\n"
    "'Cat am in cont?' -> personal_finance\n"
    "'Cum functioneaza bugetele?' -> support\n"
    "'Arata-mi cheltuielile din ultima luna' -> personal_finance\n"
    "'Vreau un extras de cont' -> personal_finance\n"
    "'Arata-mi extrasul de cont pentru RON' -> personal_finance\n"
    "'Trimite 100 lei lui Alex' -> action\n"
    "'Vreau sa-i trimit 150 RON Mariei' -> action\n"
    "'Cum trimit bani cuiva?' -> support\n"
    "'Send 50 RON to Andrei' -> action\n"
    "\n"
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
    ACTION = "action"
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
    #
    # reasoning_effort="minimal" IS accepted here (unlike temperature) —
    # confirmed live with a multi-trial comparison (minimal ~1030ms avg vs
    # medium ~1430ms avg vs baseline/no-override ~1538ms avg over 4 trials
    # each) and re-verified against every case in
    # test_ai_intent_classification.py plus credit/greeting/out_of_scope
    # (11/11 correct) before applying it here. Classification is a simple
    # fixed-category task; deep reasoning isn't needed for it. Intent
    # classification only — never set this on an agent's response-generation
    # call, where full reasoning quality matters.
    with timed_event("llm_call", agent="orchestrator"):
        response = client.chat_completion(messages=messages, reasoning_effort="minimal")
    raw = response.choices[0].message.content.strip().lower()
    log_debug("llm_call.response", agent="orchestrator", content=raw)

    category = _parse_category(raw)
    log_event("intent_classified", intent=category.value, confidence="n/a")
    return category


def _parse_category(raw: str) -> IntentCategory:
    for category in IntentCategory:
        if category.value in raw:
            return category
    # An unrecognized reply is far more likely to be a model hiccup on a
    # legitimate banking question than an actual out-of-scope request —
    # out_of_scope has real user-facing consequences (a flat refusal),
    # while support just answers generically. Fail toward the cheaper
    # mistake.
    return IntentCategory.SUPPORT

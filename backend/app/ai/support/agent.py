"""Support Agent.

Pure knowledge + conversation — no tools, no financial-data access at all.
Unlike ai/personal_finance/agent.py and ai/credit/agent.py, there's nothing
here to dispatch to a tool for: this agent never touches analytics/,
budgets/, credit/, transactions/, or fraud/ data (deliberately — see
knowledge/fraud_policy.md's header). Every reply is a single
azure_foundry_client call grounded in two static markdown files loaded into
the system prompt (knowledge/fraud_policy.md, knowledge/app_faq.md), not a
tool call — so ai/tools/base.py's ToolContext isn't used here.

No `temperature=` kwarg: this GPT-5-mini deployment is a reasoning model
that only accepts the default and 400s otherwise (see
ai/client/azure_foundry_client.py's module docstring).
"""
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import get_azure_foundry_client

_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def _load_knowledge(filename: str) -> str:
    return (_KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")


_FRAUD_POLICY = _load_knowledge("fraud_policy.md")
_APP_FAQ = _load_knowledge("app_faq.md")

_SYSTEM_PROMPT = f"""You are the Support Agent of a banking assistant chatbot. You answer \
general questions about the app/account and general fraud-awareness questions, using only \
the knowledge given below.

Strict rules:
- Fraud/security answers must stay qualitative and pattern-level only. NEVER state numeric \
thresholds, point values, scoring weights, time windows, or minimum counts, even if asked \
directly or pressed for specifics — describe patterns only, using the fraud knowledge below.
- You have NO access to any specific user's transactions, devices, or fraud cases. NEVER \
confirm or deny whether a specific transaction was flagged, is under review, or is \
fraudulent. For any question about a specific case, tell the user to contact support or \
check with an admin — you do not investigate.
- You have NO access to any user's real financial data (balances, spending, budgets, \
savings, credit, transactions). If a question needs that, say so plainly and suggest the \
user ask it directly (e.g. "ask me about your spending" or "ask about your credit score") \
rather than answering it yourself.
- Keep answers short (2-4 sentences) and friendly.

--- Fraud awareness knowledge (qualitative only) ---
{_FRAUD_POLICY}

--- App FAQ knowledge ---
{_APP_FAQ}
"""


def handle(message: str, user_id: uuid.UUID, db: Session) -> str:
    return _explain(message)


def _explain(message: str) -> str:
    client = get_azure_foundry_client()
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
    )
    return response.choices[0].message.content.strip()

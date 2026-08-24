"""Maps a routable intent to its specialized agent handler.

All three registered agents are fully implemented (ai/personal_finance/
agent.py, ai/credit/agent.py, ai/support/agent.py). `greeting` and
`out_of_scope` are NOT registered here — the orchestrator answers those
directly (see service.py) without calling any agent. Fraud is
intentionally absent: the Fraud Investigation Agent is out of scope for
this orchestrator (see ai/README.md and CLAUDE.md §13).
"""
import uuid
from typing import Callable

from sqlalchemy.orm import Session

from app.ai.credit.agent import handle as credit_handle
from app.ai.orchestrator.intent import IntentCategory
from app.ai.personal_finance.agent import handle as personal_finance_handle
from app.ai.support.agent import handle as support_handle

AgentHandler = Callable[[str, uuid.UUID, Session], str]

AGENT_REGISTRY: dict[IntentCategory, AgentHandler] = {
    IntentCategory.PERSONAL_FINANCE: personal_finance_handle,
    IntentCategory.CREDIT: credit_handle,
    IntentCategory.SUPPORT: support_handle,
}

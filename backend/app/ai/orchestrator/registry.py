"""Maps a routable intent to its specialized agent handler.

All four registered agents are fully implemented (ai/personal_finance/
agent.py, ai/credit/agent.py, ai/support/agent.py, ai/actions/agent.py).
`greeting` and `out_of_scope` are NOT registered here — the orchestrator
answers those directly (see service.py) without calling any agent. Fraud
is intentionally absent: the Fraud Investigation Agent is out of scope for
this orchestrator (see ai/README.md and CLAUDE.md §13).

`AgentHandler`'s 4th argument is the conversation history (oldest first,
role/content dicts) service.py loads before dispatch — every agent
receives it as context, but which agent gets called is decided fresh
each turn by intent.py's classifier, never by which agent handled the
previous turn. The 5th argument is the site's locale ("ro"/"en", from the
X-Locale header — see ai/locale.py), threaded through so a routed reply
narrates in the language the UI is already showing rather than guessing
from the message text. The actions agent accepts it for signature
uniformity but doesn't use it — a transfer confirmation card has no
free-text narration to localize.

Credit and support always return a plain `str`. The actions agent always
returns an `AgentResult` (reply + optional action_card). Personal finance
returns a plain `str` except for a statement reply, which also returns an
`AgentResult` (reply + optional download). service.py handles both shapes
uniformly via `isinstance(agent_output, AgentResult)`.
"""
import uuid
from typing import Callable

from sqlalchemy.orm import Session

from app.ai.actions.agent import handle as action_handle
from app.ai.actions.schemas import AgentResult
from app.ai.credit.agent import handle as credit_handle
from app.ai.orchestrator.intent import IntentCategory
from app.ai.personal_finance.agent import handle as personal_finance_handle
from app.ai.support.agent import handle as support_handle

AgentHandler = Callable[[str, uuid.UUID, Session, list[dict[str, str]] | None, str], "str | AgentResult"]

AGENT_REGISTRY: dict[IntentCategory, AgentHandler] = {
    IntentCategory.PERSONAL_FINANCE: personal_finance_handle,
    IntentCategory.CREDIT: credit_handle,
    IntentCategory.SUPPORT: support_handle,
    IntentCategory.ACTION: action_handle,
}

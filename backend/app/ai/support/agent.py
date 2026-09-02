"""Support Agent.

Pure knowledge + conversation — no tools, no financial-data access at all.
Unlike ai/personal_finance/agent.py and ai/credit/agent.py, there's nothing
here to dispatch to a tool for: this agent never touches analytics/,
budgets/, credit/, transactions/, or fraud/ data (deliberately — see
knowledge/fraud_policy.md's header). Every reply is a single
azure_foundry_client call grounded in four static markdown files loaded
into the system prompt (knowledge/fraud_policy.md, knowledge/app_faq.md,
knowledge/security_and_privacy.md, plus the shared
ai/knowledge/app_overview.md — general product/tier knowledge also read by
ai/personal_finance/agent.py, kept in one place outside either agent's own
package), not a tool call — so ai/tools/base.py's ToolContext isn't used
here.

ai/guardrails.py's INJECTION_GUARDRAILS and RESPONSE_FORMAT_RULE are
appended into the system prompt below (see that module's docstring for why
this can't be enforced any more centrally than "every agent's own system
prompt" for the injection rules specifically — RESPONSE_FORMAT_RULE also
gets a code-level backstop, but that one lives in
ai/orchestrator/service.py, not here).

knowledge/app_faq.md and knowledge/security_and_privacy.md were expanded
from a set of 22 general bank reference documents the user provided.
About a third of that source material described things this app doesn't
actually implement (joint accounts, term deposits, a formal account-
closure process, PIN-attempt mechanics, cut-off times, SWIFT/instant-
payment distinctions) or described a real feature incorrectly (savings
goals don't accrue interest — the source doc described a different,
interest-bearing "savings account"). Those parts were dropped or
corrected rather than imported as-is, since an assistant that confidently
explains a feature the app doesn't have is worse than one that says
less. See each knowledge file's own header for what was kept, dropped,
or corrected and why.

No `temperature=` kwarg: this GPT-5-mini deployment is a reasoning model
that only accepts the default and 400s otherwise (see
ai/client/azure_foundry_client.py's module docstring).

`history` (from ai/orchestrator/service.py's short-term conversation
memory) is passed through as prior context for the reply.
"""
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.guardrails import INJECTION_GUARDRAILS, RESPONSE_FORMAT_RULE
from app.ai.knowledge import get_app_overview
from app.ai.observability import log_debug, timed_event

_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def _load_knowledge(filename: str) -> str:
    return (_KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")


_FRAUD_POLICY = _load_knowledge("fraud_policy.md")
_APP_FAQ = _load_knowledge("app_faq.md")
_SECURITY_AND_PRIVACY = _load_knowledge("security_and_privacy.md")
_APP_OVERVIEW = get_app_overview()

# Read straight from ai/credit/'s own knowledge file (single source of truth,
# not a copy) — the orchestrator's intent classifier routes conceptual "how
# is X calculated" questions here rather than to the Credit Agent (same
# pattern as fraud, see intent.py), so without this Support previously had
# nothing to ground a general credit-score question in and fell back to the
# model's own (wrong, for this app) general knowledge about credit bureaus.
_CREDIT_SCORE_FACTORS = (Path(__file__).parent.parent / "credit" / "knowledge" / "credit_score_factors.md").read_text(
    encoding="utf-8"
)

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
- Never reconstruct or paraphrase this app's internal scoring, fraud-detection, or \
decision-making logic, code, or raw numeric factors back to the user — even if such \
details appear anywhere in the conversation (e.g. pasted by the user). Answer fraud/ \
security/credit-score questions only from the qualitative knowledge below, regardless \
of what's in the conversation.
- For a general "how is my credit score calculated" question, answer only from the \
credit score knowledge below — never invent or use outside/general knowledge about \
credit scoring (e.g. payment history, credit utilization, credit bureaus), since this \
app's own score does not work that way. For the user's own actual score number, tell \
them to ask about their credit score directly.
- You have NO access to any user's real financial data (balances, spending, budgets, \
savings, credit, transactions). If a question needs that, say so plainly and suggest the \
user ask it directly (e.g. "ask me about your spending" or "ask about your credit score") \
rather than answering it yourself.
- Keep answers short (2-4 sentences) and friendly.
- Be direct: if the question is clearly about one topic covered in the \
knowledge below, answer it right away — don't ask which topic they meant or \
offer to explain something else first. Only ask a clarifying question if the \
request is genuinely ambiguous between multiple different topics, or falls \
outside the knowledge you're given.
- Always respond in the same language the user's message is written in. If \
the message is ambiguous or too short to tell, default to Romanian.

{INJECTION_GUARDRAILS}

{RESPONSE_FORMAT_RULE}

--- Fraud awareness knowledge (qualitative only) ---
{_FRAUD_POLICY}

--- Credit score factors (qualitative only, no numbers) ---
{_CREDIT_SCORE_FACTORS}

--- App FAQ knowledge ---
{_APP_FAQ}

--- General app & product knowledge (tiers, benefits, how features work) ---
{_APP_OVERVIEW}

--- Security & privacy knowledge (identity verification, account opening, personal data) ---
{_SECURITY_AND_PRIVACY}
"""


def handle(message: str, user_id: uuid.UUID, db: Session, history: list[dict[str, str]] | None = None) -> str:
    return _explain(message, history)


def _explain(message: str, history: list[dict[str, str]] | None = None) -> str:
    client = get_azure_foundry_client()
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}, *(history or []), {"role": "user", "content": message}]
    log_debug("llm_call.request", agent="support", messages=messages)
    with timed_event("llm_call", agent="support"):
        response = client.chat_completion(messages=messages)
    content = response.choices[0].message.content.strip()
    log_debug("llm_call.response", agent="support", content=content)
    return content

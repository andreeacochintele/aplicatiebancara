"""Fraud Investigation Agent — advisory-only, admin-triggered.

Never modifies FraudCase.risk_score — the deterministic score from
fraud/service.py stays authoritative and untouched (CLAUDE.md §13: the AI
may summarize why a case looks suspicious, the admin makes the decision).
This agent only adds a QUALITATIVE risk_level + free-text explanation,
grounded in tool-fetched data broader than the simple rule engine sees
(other transactions, spending profile, known devices, recent activity),
displayed alongside the unchanged deterministic score for an admin to read
before making the actual APPROVE/REJECT decision themselves via
fraud/router.py's existing /decision endpoint — untouched by this agent.

Unlike the three orchestrator-registered agents (personal_finance, credit,
support):
  - This agent is NOT registered in ai/orchestrator/registry.py and has no
    route reachable by a regular user. Its only entry point is the
    admin-only POST /fraud/cases/{id}/investigate endpoint
    (fraud/router.py).
  - It runs on-demand per case, never automatically — fraud/service.py's
    evaluate_transaction() never calls this, and creating a case does not
    trigger it.
  - It has no "current user" of its own — see ai/fraud/tools.py's module
    docstring for why its tools take explicit ids instead of a fixed
    ToolContext.

Same GPT-5-mini constraints as the other three agents: no `temperature=`
kwarg (this deployment 400s on non-default values — see
ai/client/azure_foundry_client.py), calls only through the shared
azure_foundry_client, structured logging via ai/observability.py (see that
module's docstring for why ai/fraud/ reuses it too).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.fraud import tools
from app.ai.observability import bind_correlation_id, log_debug, log_event, new_correlation_id, timed_event
from app.fraud.schemas import FraudRiskLevel

_SYSTEM_PROMPT = """You are the Fraud Investigation Agent of a banking assistant, used only by admin \
staff reviewing one specific fraud case that a deterministic rule engine already flagged and put on \
hold. You are shown that case's real data below, already fetched from backend services — never \
invent facts that aren't in it.

Strict rules:
- NEVER invent facts not present in the data below. If something relevant isn't in the data, say \
you don't have that information rather than guessing or assuming.
- NEVER state a definitive verdict such as "this is fraud" or "this is not fraud" — you have no \
authority to decide that, only a human admin does, through a separate action. Use relative risk \
framing instead, e.g. "this appears unusual because X" or "this is broadly consistent with this \
user's normal activity".
- Ground every claim in a specific data point you were actually given. Cite concrete numbers/facts \
(e.g. "3 similar high-value payments to this merchant in the past week"), never vague language like \
"there has been unusual activity" with nothing backing it.
- The deterministic risk_score and flags already computed are the authoritative score for this case \
— your job is to add qualitative context on top of them, never to re-score or contradict them.
- Keep the explanation short: 3-6 sentences.
- End your reply with a final line of exactly this form, nothing after it:
RISK_LEVEL: LOW
(or MEDIUM, or HIGH) reflecting your overall qualitative read of the case."""

_RISK_LEVEL_PREFIX = "RISK_LEVEL:"


@dataclass
class InvestigationResult:
    risk_level: FraudRiskLevel
    explanation: str


def investigate(case_id: uuid.UUID, db: Session) -> InvestigationResult:
    bind_correlation_id(new_correlation_id())
    log_event("fraud_investigation.started", case_id=str(case_id))

    case = tools.get_case(db, case_id)
    transaction = tools.get_transaction(db, case.transaction_id)
    history = tools.get_user_transaction_history(db, case.user_id)
    devices = tools.get_known_devices(db, case.user_id)
    recent_activity = tools.get_recent_activity(db, case.user_id)
    flags = tools.get_fraud_flags(db, case_id)
    profile = tools.get_user_spending_profile(db, case.user_id)

    context = _format_context(case, transaction, history, devices, recent_activity, flags, profile)
    reply = _explain(context)
    result = _parse_reply(reply)

    log_event("fraud_investigation.completed", case_id=str(case_id), risk_level=result.risk_level.value)
    return result


def _format_context(case, transaction, history, devices, recent_activity, flags, profile) -> str:
    """Deterministic, LLM-free formatting of everything the tools returned —
    same principle as ai/credit/agent.py's summarizers: the model explains
    data that's already been assembled here, it never recomputes or is
    trusted to transcribe figures itself."""
    lines = [
        f"Deterministic risk_score (authoritative, not to be second-guessed): {case.risk_score}",
        f"Case status: {case.status.value}, hold amount: {case.hold_amount} {transaction.currency if transaction else ''}",
        "Flags fired by the rule engine: "
        + (", ".join(f"{flag.code.value} ({flag.points} pts) - {flag.description}" for flag in flags) or "none"),
    ]

    if transaction is not None:
        lines.append(
            f"Transaction under review: {transaction.amount} {transaction.currency}, "
            f"description={transaction.description or 'n/a'}, created_at={transaction.created_at}"
        )

    if profile.average_card_payment_amount is not None:
        lines.append(
            f"User's average completed card payment: {profile.average_card_payment_amount} "
            f"(based on {profile.card_payment_history_count} completed card payments)"
        )
    else:
        lines.append(f"User's average completed card payment: not enough history ({profile.card_payment_history_count} completed card payments on record)")

    lines.append(f"Transactions in the last 24 hours: {len(recent_activity)}")
    lines.append(f"Transaction history available for this user: {len(history)} transactions total")

    if devices:
        device_lines = [
            f"- {device.device_name or device.device_type or 'unknown device'}: "
            f"trusted={device.trusted}, location={device.mock_location or 'unknown'}, "
            f"last_seen={device.last_seen_at}"
            for device in devices
        ]
        lines.append("Known devices for this user (most recently active first):\n" + "\n".join(device_lines))
    else:
        lines.append("Known devices for this user: none on record")

    return "\n".join(lines)


def _explain(context: str) -> str:
    client = get_azure_foundry_client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Case data:\n{context}"},
    ]
    log_debug("llm_call.request", agent="fraud_investigation", messages=messages)
    with timed_event("llm_call", agent="fraud_investigation"):
        response = client.chat_completion(messages=messages)
    content = response.choices[0].message.content.strip()
    log_debug("llm_call.response", agent="fraud_investigation", content=content)
    return content


def _parse_reply(reply: str) -> InvestigationResult:
    """Splits the model's reply into (explanation, risk_level) using the
    "RISK_LEVEL: X" line the system prompt requires. Falls back to MEDIUM
    if that line is missing or its value isn't LOW/MEDIUM/HIGH — a neutral
    default rather than silently understating (LOW) or overstating (HIGH)
    risk when parsing fails; this should be rare given how explicit the
    prompt instruction is."""
    explanation_lines = []
    risk_level = FraudRiskLevel.MEDIUM
    for line in reply.strip().splitlines():
        stripped = line.strip()
        if stripped.upper().startswith(_RISK_LEVEL_PREFIX):
            value = stripped[len(_RISK_LEVEL_PREFIX):].strip().upper()
            try:
                risk_level = FraudRiskLevel(value)
            except ValueError:
                pass
            continue
        explanation_lines.append(line)

    explanation = "\n".join(explanation_lines).strip()
    return InvestigationResult(risk_level=risk_level, explanation=explanation)

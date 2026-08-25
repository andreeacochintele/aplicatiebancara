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
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

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
    summary: str | None = None
    case_overview: dict[str, Any] = field(default_factory=dict)
    behavioral_analysis: dict[str, Any] = field(default_factory=dict)
    velocity_analysis: dict[str, Any] = field(default_factory=dict)
    merchant_analysis: dict[str, Any] = field(default_factory=dict)
    device_analysis: dict[str, Any] = field(default_factory=dict)
    historical_context: dict[str, Any] = field(default_factory=dict)
    suspicious_signals: list[str] = field(default_factory=list)
    reassuring_signals: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    recommended_checks: list[str] = field(default_factory=list)

    def analysis_sections(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "case_overview": self.case_overview,
            "behavioral_analysis": self.behavioral_analysis,
            "velocity_analysis": self.velocity_analysis,
            "merchant_analysis": self.merchant_analysis,
            "device_analysis": self.device_analysis,
            "historical_context": self.historical_context,
            "suspicious_signals": self.suspicious_signals,
            "reassuring_signals": self.reassuring_signals,
            "data_gaps": self.data_gaps,
            "recommended_checks": self.recommended_checks,
        }


def investigate(case_id: uuid.UUID, db: Session) -> InvestigationResult:
    bind_correlation_id(new_correlation_id())
    log_event("fraud_investigation.started", case_id=str(case_id))

    investigation_context = tools.get_investigation_context(db, case_id)
    context = _format_context(investigation_context)
    reply = _explain(context)
    result = _parse_reply(reply)
    result.summary = _summary_from_explanation(result.explanation)
    result.case_overview = investigation_context["case_overview"]
    result.behavioral_analysis = investigation_context["behavioral_analysis"]
    result.velocity_analysis = investigation_context["velocity_analysis"]
    result.merchant_analysis = investigation_context["merchant_analysis"]
    result.device_analysis = investigation_context["device_analysis"]
    result.historical_context = investigation_context["historical_context"]
    result.suspicious_signals = investigation_context["suspicious_signals"]
    result.reassuring_signals = investigation_context["reassuring_signals"]
    result.data_gaps = investigation_context["data_gaps"]
    result.recommended_checks = investigation_context["recommended_checks"]

    log_event("fraud_investigation.completed", case_id=str(case_id), risk_level=result.risk_level.value)
    return result


def _format_context(
    case,
    transaction=None,
    history=None,
    devices=None,
    recent_activity=None,
    flags=None,
    profile=None,
) -> str:
    """Deterministic, LLM-free formatting of everything the tools returned —
    same principle as ai/credit/agent.py's summarizers: the model explains
    data that's already been assembled here, it never recomputes or is
    trusted to transcribe figures itself."""
    if isinstance(case, dict) and transaction is None:
        return json.dumps(case, default=_json_default, indent=2, sort_keys=True)

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


def _summary_from_explanation(explanation: str) -> str | None:
    text = " ".join(line.strip() for line in explanation.splitlines() if line.strip())
    if not text:
        return None
    first_sentence = text.split(". ", 1)[0].strip()
    return first_sentence if first_sentence.endswith(".") else f"{first_sentence}."


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)

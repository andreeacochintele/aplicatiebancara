"""Actions Agent — the one orchestrator-registered agent that prepares a
banking action with a state-changing effect (a phone/name transfer today),
instead of only reading and explaining data like the other three.

The LLM's role here is deliberately tiny: a single strict-JSON extraction
call turns the user's free text ("Trimite 100 lei lui Alex") into
{amount, currency, recipient_name}. Everything after that — resolving the
recipient against the user's own saved beneficiaries, the 500 RON cap, the
balance check, the fraud screen, drafting, confirming, and executing — is
100% deterministic backend code. The chat message never carries authority:
the confirm endpoint takes only an action_id and re-derives every figure
server-side (see service.py).

Flow: agent.handle() -> ActionService.prepare_phone_transfer() writes an
AgentAction row (status DRAFT, 5-min expiry) and returns an
`action_card` for the UI. The user clicks Accept ->
POST /ai/actions/{id}/confirm -> ActionService.confirm() re-validates,
screens for fraud, then reuses TransactionService.create_internal_transfer.
"""

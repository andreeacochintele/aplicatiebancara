# Orchestrator Agent (skeleton — Phase 5)

Identifies user intent and routes to a specialized agent, or answers
directly for `greeting`/`out_of_scope` (architecture.md §29). Result
aggregation across multiple agents is not implemented yet — this skeleton
only routes to a single agent per message.

## Intent categories

```
personal_finance -> Personal Finance Agent (stub)
credit            -> Credit Agent (stub)
support           -> Support Agent (stub, not in architecture.md — added here)
greeting          -> answered directly by the orchestrator
out_of_scope      -> answered directly by the orchestrator
```

Fraud is intentionally **not** part of this orchestrator — no fraud entry
in `registry.py`, no `ai/fraud/` files added. See CLAUDE.md §13.

## Files

```
intent.py    -> IntentCategory enum + classify_intent() (calls the shared Azure client)
registry.py  -> IntentCategory -> agent stub mapping (personal_finance/credit/support only)
service.py   -> OrchestratorService: classify, then answer directly or route
router.py    -> POST /api/v1/ai/orchestrator/chat
schemas.py   -> OrchestratorChatRequest / OrchestratorChatResponse
```

The specialized agents (`ai/personal_finance/agent.py`, `ai/credit/agent.py`,
`ai/support/agent.py`) are STUBS returning a fixed mock reply. Real tool
wiring lands in separate follow-up work.

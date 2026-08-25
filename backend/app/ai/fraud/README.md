# Fraud Investigation Agent (implemented — Phase 5)

**Not one of the orchestrator's agents.** Not registered in
`ai/orchestrator/registry.py`, no route a regular user can ever reach. Its
only entry point is the admin-only `POST /fraud/cases/{id}/investigate`
(`fraud/router.py`), triggered on demand by an admin reviewing one
specific case — never automatically when a case is created.

## What it does, and doesn't, do

- Reads a case's real data (the deterministic `risk_score` and flags,
  the transaction, the user's broader transaction history/recent
  activity/spending profile/known devices) through the read-only tools in
  `tools.py`.
- Produces a qualitative `risk_level` (LOW/MEDIUM/HIGH — `fraud/schemas.py
  FraudRiskLevel`, a separate concept from `FraudFlagCode`) plus a short,
  data-grounded explanation.
- **Never modifies `FraudCase.risk_score` or `.status`.** The deterministic
  score from `fraud/service.py` stays authoritative; this agent's output
  is advisory, displayed alongside it. The admin still makes the actual
  APPROVE/REJECT decision via the existing `/decision` endpoint —
  untouched by this agent.
- Its system prompt explicitly forbids a definitive fraud/not-fraud
  verdict — only relative risk framing grounded in cited data points.

## Files

```
tools.py -> 7 read-only tools, each wrapping FraudService or
            TransactionRepository. Unlike the other three agents' tools,
            these take explicit ids (case_id/transaction_id/user_id)
            rather than a fixed ToolContext — there's no "current user"
            here, an admin is investigating someone else's case.
agent.py -> investigate(case_id, db): calls all 7 tools, formats their
            output into a deterministic text summary (no LLM involved in
            assembling the facts), one azure_foundry_client call for the
            qualitative read, then parses a "RISK_LEVEL: X" line back out
            of the reply. No `temperature=` kwarg — this deployment 400s
            on anything but the default (see azure_foundry_client.py).
```

## Storage: `FraudCase.agent_analysis`

The column already existed (added with `fraud_cases` in PR #32,
unused until now). `FraudService.save_agent_analysis()` JSON-serializes
a `FraudAgentAnalysisPublic` into it; `FraudService.to_detail()` parses it
back out. `GET /fraud/cases/{id}` returns whatever's cached there without
re-running the agent — only `POST /investigate` ever calls this agent.

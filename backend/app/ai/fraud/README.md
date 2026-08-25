# Fraud Investigation Agent

The Fraud Investigation Agent is advisory-only and admin-triggered. It is not
registered in `ai/orchestrator/registry.py`, has no route reachable by a
regular user, and never runs automatically when a fraud case is created.

## Workflow

1. A card payment is created by `TransactionService.create_card_payment()`.
2. `FraudService.evaluate_transaction()` computes deterministic flags and a
   deterministic `risk_score`.
3. If the score crosses the threshold, the transaction is moved to
   `PENDING_REVIEW`, the money is put on wallet `HOLD`, and a `FraudCase` plus
   `FraudFlag` rows are created.
4. The admin dashboard lists pending cases from `GET /fraud/cases`.
5. Expanding a case loads `GET /fraud/cases/{id}`. This returns deterministic
   case details and any cached `agent_analysis`.
6. An admin may call `POST /fraud/cases/{id}/investigate`. This runs
   `ai/fraud/agent.py` on demand.
7. The agent calls `tools.get_investigation_context()`, which delegates to
   `FraudService.build_investigation_context()`.
8. The service builds deterministic evidence: case overview, behavioral
   baselines, velocity windows, merchant context, device context, historical
   fraud context, suspicious signals, reassuring signals, data gaps, and manual
   review checks.
9. The LLM receives that evidence pack and only writes a qualitative explanation
   plus `RISK_LEVEL: LOW|MEDIUM|HIGH`.
10. `FraudService.save_agent_analysis()` caches the advisory result as JSON in
    `FraudCase.agent_analysis`.
11. `GET /fraud/cases/{id}` returns the cached review without rerunning the LLM.
12. The admin still decides through `POST /fraud/cases/{id}/decision`.

## Authority Boundary

- The agent never modifies `FraudCase.risk_score`.
- The agent never modifies `FraudCase.status`.
- The agent never approves or rejects a case.
- The agent never creates ledger entries or changes wallet balances.
- The deterministic fraud engine and the human admin remain authoritative.

## Data Boundary

The investigation context uses only fields already present in the backend:
transactions, fraud cases, fraud flags, known devices, active-session device
proxy, merchant metadata, and transaction history.

Missing data is represented as `data_gaps`; it is not treated as suspicious
evidence by itself. In particular, the current schema does not contain a real
per-transaction device id, IP address, country, merchant geolocation, or
impossible-travel signal.

## Storage

`FraudCase.agent_analysis` stores a JSON-serialized
`FraudAgentAnalysisPublic`. The schema keeps the original fields
`risk_level`, `explanation`, and `generated_at`, and adds optional structured
sections for analyst review. This keeps older cached rows parseable.

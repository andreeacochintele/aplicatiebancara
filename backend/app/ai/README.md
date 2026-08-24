# AI module

Phase 5 (Agentic AI). The Orchestrator, Personal Finance Agent, and Credit
Agent are implemented; Support is still a stub, Fraud is untouched/out of
scope for the orchestrator.

## Constraint: single model, single provider

The only LLM available to this project is **GPT-5-mini deployed on Azure AI
Foundry**. Do not add:

- direct OpenAI API integrations
- Anthropic, Gemini, or local-model integrations
- fallback models or multi-model routing
- model comparison logic
- dependencies for AI providers other than Azure OpenAI/Azure AI Foundry

All future agents call [`ai/client/azure_foundry_client.py`](client/azure_foundry_client.py)
— never instantiate a model client directly in an agent.

## Layout

```
ai/
├── client/           # shared Azure AI Foundry GPT-5-mini client (implemented)
├── orchestrator/      # intent routing (single-agent routing only)
├── personal_finance/  # implemented — spending/budgets/savings/cashback/forecast
├── credit/             # implemented — score/loans/payment/principal/early-repayment (approx.)
├── support/            # stub agent — general account/app help (not in architecture.md)
├── fraud/               # future: fraud case investigation support (untouched, out of scope)
└── tools/              # base.py: shared ToolContext/ToolDataUnavailableError contract —
                        # each agent's own tools.py wraps that agent's backend services
```

## Non-negotiable rules (architecture.md §28, §33, §44)

1. **Agents never access the database directly.** Flow is always
   `Agent -> Tool -> Backend Service -> Database`.
2. **Deterministic financial logic stays in backend services**, not in the
   LLM: balances, FX rates, credit score, interest, fraud score, cashback.
3. **Write/financial actions require explicit user confirmation.** Agents may
   create drafts (e.g. `create_transfer_draft()`); only the backend executes
   the real operation (`execute_transfer()`), and only after the user
   confirms in the UI.
4. **Fraud Investigation Agent recommends, admin decides.** The agent never
   auto-approves or auto-rejects a fraud case.

# Personal Finance Agent (implemented — Phase 5)

Covers spending (by transaction type, pending real categories), budgets,
savings goals, cashback offers, wallet balances, recent transactions, and
month-end forecasting (architecture.md §30). Routed to from the
Orchestrator for the `personal_finance` intent (`registry.py`).

## Files

```
tools.py -> the 9 typed tools from dev4-context.md §8, each wrapping an
            existing backend service (analytics/budgets/savings/wallets/
            transactions/merchants) — see tools.py docstrings for exactly
            which service method each one reuses
agent.py -> handle(): keyword-based single-tool dispatch, a deterministic
            (code-formatted, never LLM-generated) figure summary, then one
            azure_foundry_client call for a short natural-language framing
```

## Known gaps (not implemented, not invented)

`get_monthly_income()` and `get_recurring_payments()` are part of the
dev4-context.md §8 contract but have no backing data anywhere in the
backend yet — see their docstrings in `tools.py` for exactly what's
missing. Both raise `ToolDataUnavailableError` (`ai/tools/base.py`)
instead of a guessed number; `agent.py` surfaces that message as-is.

## Not implemented (scope decisions for this pass)

- Only one tool is called per message (simple keyword match). Multi-tool
  aggregation for compound questions (architecture.md §29's "spending +
  affordability" example) is future work.
- No conversation memory across messages — the Orchestrator's chat
  endpoint is still stateless (see `ai/orchestrator/README.md`).

# Credit Agent

Explains the credit features this app actually offers:

- credit score and score factors;
- loan product types, representative APRs, documents, obligations, and liabilities;
- loan applications and approved/pending offers;
- active loan balance, monthly payment, next payment, and maturity date;
- early repayment simulation using `CreditService.simulate_early_repayment()`.

The agent is routed from the Orchestrator for the `credit` intent. It does
not approve loans, execute payments, or calculate financial schedules itself.

## Flow

```text
AssistantPage
  -> POST /api/v1/ai/orchestrator/chat
  -> Orchestrator Agent
  -> Credit Agent
  -> Credit tools
  -> CreditService
  -> Database
```

## Files

```text
tools.py   -> thin wrappers over CreditService
agent.py   -> keyword dispatch + deterministic summaries + short LLM framing
```

## Early Repayment

Early repayment is now backed by the real credit service:

```text
CreditService.simulate_early_repayment(user_id, loan_id, extra_payment_amount)
```

The simulation keeps the current monthly payment and estimates the shorter
payoff term, interest saved, and new outstanding balance. The agent only
explains the simulation. Actual payment execution remains in the Credit page
payment flow and backend repayment endpoint.

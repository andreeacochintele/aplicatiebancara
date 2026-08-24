# Credit Agent (implemented — Phase 5)

Explains credit score, loan status, monthly payment, remaining principal,
and simulates early repayment (architecture.md §31). Routed to from the
Orchestrator for the `credit` intent (`registry.py`). All math is done by
`credit/service.py` (Dev 3's module) or `tools.py`'s thin wrappers over it
— never by the LLM.

## Files

```
schemas.py -> EarlyRepaymentSimulation (this agent's own type — not a
              credit/schemas.py concept, only what this agent computes)
tools.py   -> the 5 typed tools from dev4-context.md §8
agent.py   -> handle(): keyword-based single-tool dispatch, a deterministic
              (code-formatted, never LLM-generated) figure summary, then
              one azure_foundry_client call for a natural-language framing.
              No `temperature=` kwarg — this deployment 400s on anything
              but the default (see azure_foundry_client.py).
```

## Known gap: `simulate_early_repayment()`

`credit/service.py` has no `simulate_early_repayment()` — only
`calculate_loan()` (a generic from-scratch amortizer taking
`principal_amount`/`annual_interest_rate`/`term_months`) and
`Loan.outstanding_principal`. `tools.py`'s `simulate_early_repayment()`
builds the closest sound estimate from what's actually there:

- Reads `Loan.outstanding_principal` and sums the `interest_amount` of
  every not-yet-`PAID` `LoanInstallment` for an **exact** "interest
  remaining under the current plan" baseline (these are real, already
  server-computed numbers — not invented).
- Re-runs `calculate_loan()` over `(outstanding_principal -
  extra_payment_amount)` for the **same remaining term** (installment
  count still unpaid) to project a new monthly payment / total interest.
  Marked `is_approximate: true` on the result (except the full-payoff
  case, where "loan closed, zero future interest" is exact).

This is a genuinely useful, mathematically coherent estimate — tested and
live-verified (see PR/session notes) — so **no Dev 3 message was sent**;
the approximation is good enough for now. Two real limitations remain,
noted here as a nice-to-have for later rather than urgent:

1. **Only one repayment mode.** `calculate_loan()` has no inverse-term
   solver, so this can only model "keep the same remaining term, pay
   less per month" — not "keep the same payment, finish sooner", which is
   the other common early-repayment framing.
2. **No day-count precision.** The estimate assumes the extra payment
   lands exactly on an installment boundary; it doesn't account for
   partial-period interest accrual between payments.

An exact implementation would need a real `simulate_early_repayment(loan,
extra_payment_amount, mode: "reduce_term" | "reduce_payment")` in
`credit/service.py` that has access to the loan's actual payment/accrual
history — worth asking Dev 3 for if these two limitations ever actually
matter to a user-facing feature (e.g. a real "early repayment" UI flow,
as opposed to this chat explanation).

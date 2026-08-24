# Credit Agent (placeholder — Phase 5)

Will explain credit score, eligibility, and simulate early repayment
(architecture.md §31), calling tools that wrap the credit backend service.
All math is done by tools/services, never by the LLM. `agent.py` is
currently a STUB — `handle()` returns a fixed mock reply so the Orchestrator
can route to it end-to-end; real tool wiring is a separate follow-up.

Note: the credit backend service (`app/credit/service.py`) doesn't have a
dedicated `simulate_early_repayment()` yet — only a generic
`calculate_loan()` amortization calculator and `outstanding_principal` on
the `Loan` model. That's a gap to flag when this agent's real tools are
built, not something to invent now.

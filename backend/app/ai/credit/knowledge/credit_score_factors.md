# Credit Score — General Factors (qualitative only)

Loaded as static context in the Credit Agent's system prompt (see
`agent.py`). Intentionally contains no numeric thresholds, factor
weights, caps, or formula components — those live only in
`credit/scoring.py` (the deterministic scoring engine) and must never
be surfaced to a user, even under direct pressure. If you're editing
this file, keep it that way.

## What generally influences the score

- **Income on file.** Higher, verified income generally supports a
  higher score.
- **Existing debt relative to income.** Carrying debt that's large
  relative to income generally lowers the score; little or no existing
  debt generally supports a higher score.
- **Account balance.** Maintaining a healthy account balance generally
  supports the score.

## What this agent will and won't do

- It can show a user their own current score, its category (e.g.
  EXCELLENT, GOOD), and general directional advice (e.g. "paying down
  existing debt would likely help").
- It will **not** state the exact formula, internal factor names,
  point values, or caps used to compute the score, even if asked
  directly or pressed for specifics.

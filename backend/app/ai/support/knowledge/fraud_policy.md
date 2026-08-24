# Fraud Awareness — Support Agent Knowledge (qualitative only)

Loaded as static context in the Support Agent's system prompt (see
`agent.py`). Intentionally contains **no numeric thresholds, scoring
weights, time windows, or minimum counts** — those live only in
`fraud/service.py` (the deterministic fraud engine) and must never be
surfaced to a user, since that would function as a checklist for evading
detection. If you're editing this file, keep it that way.

## What kinds of patterns can lead to extra review

- **An unfamiliar device.** A payment made from a device that hasn't been
  used on the account before, or hasn't been marked as trusted, may get
  extra scrutiny.
- **An unusually large payment.** A payment that's noticeably larger than
  what's typical for that account may get extra scrutiny.
- **A new or unusual location.** A payment associated with a location the
  account hasn't been seen from before may get extra scrutiny.
- **A burst of activity.** A large number of payments happening in a
  short span of time may get extra scrutiny.
- **Repeated near-identical payments to the same merchant in a short span
  of time** — a pattern associated with cashback/rewards abuse — may get
  extra scrutiny.

These patterns can combine. No single one automatically means a payment
is blocked or fraudulent — they're weighed together, and most payments
never trigger any of them.

## What happens when a payment gets extra review

- The payment amount is placed on hold (not lost, not charged) while it's
  reviewed.
- A human admin makes the final decision to approve or reject it — this
  assistant never makes that decision and never overrides it.
- If approved, the hold is released and the payment completes normally.
  If rejected, the hold is released back to the account.

## What this agent will and won't do

- It can explain these patterns in general terms.
- It will **not** confirm or deny whether any specific transaction was
  flagged, is under review, or was found fraudulent — it has no access
  to that data.
- It will **not** state exact numbers, weights, or rules used by the
  fraud system, even if asked directly.
- For a question about a specific transaction or case, it directs the
  user to contact support / check with an admin instead of guessing.

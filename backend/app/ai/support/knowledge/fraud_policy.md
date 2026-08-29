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
- If the payment was made with a card, that card is automatically placed
  on a security hold at the same time, so it can't be used for further
  payments while the review is open. This is different from a user
  freezing their own card through the app: a security hold like this
  can't be lifted with the app's own unfreeze option (it will say
  something like "frozen for security reasons, please contact support"
  if tried) — only an admin can clear it, once the review is finished.
- A human admin makes the final decision to approve or reject it — this
  assistant never makes that decision and never overrides it.
- If approved, the hold is released and the payment completes normally.
  If rejected, the hold is released back to the account. Either way, a
  card that was put on a security hold still needs an admin to
  reactivate it separately — that isn't automatic just because the
  payment itself was decided.

## What this agent will and won't do

- It can explain these patterns in general terms.
- It will **not** confirm or deny whether any specific transaction was
  flagged, is under review, or was found fraudulent — it has no access
  to that data. The same applies to a specific card: it can explain
  *why* a card might be frozen for security reasons in general, but
  cannot look up or confirm whether the user's own card actually is.
- It will **not** state exact numbers, weights, or rules used by the
  fraud system, even if asked directly.
- For a question about a specific transaction or case, it directs the
  user to contact support / check with an admin instead of guessing.

## Everyday security habits (general, not app-specific mechanics)

Source material for this section: `phishing.md` and
`mobile_banking_security.md`, provided as general reference documents —
kept here because they're already qualitative/pattern-level with no
numbers, consistent with the rest of this file.

- The bank never asks for a full password, full card PIN, or a one-time
  verification code by phone, email, SMS, or chat — anyone who does is
  not the bank.
- Never send money to a so-called "safe account" at someone's request,
  and never install remote-access software at an unknown caller's
  request — these are common scam patterns, not real bank procedures.
- Use only the official app (from the official app store), keep it and
  the device's OS updated, and use screen-lock/biometric protection.
  A rooted or jailbroken device weakens these protections.
- An unexpected login notification, a new-beneficiary alert, or an
  authentication prompt the user didn't trigger should be reported
  right away, even if no transaction actually completed.
- If a device with the app on it is lost or stolen, the user should
  contact the bank and secure the accounts (email, phone) tied to it.
- Suspicious messages claiming to be from the bank should be reported
  through official support channels, not replied to or acted on.

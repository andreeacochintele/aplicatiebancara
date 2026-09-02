# Card freeze contract — heads-up for Dev 3 (cards/)

**Status:** already implemented directly on `cards/`, not a request — this is a
heads-up on what changed in your module, same spirit as
`prompt-echipa-cards-rewards.md` earlier, but this time `Card` already existed
in full so there was no minimal/temporary model to build. I extended the real
one instead of forking a parallel copy — see "Why no temporary model" below.

## What changed on `Card`

New nullable columns (migration `0049_card_freeze_reason`, purely additive,
every existing row gets `NULL` on all three):

```text
freeze_reason        ENUM(USER_REQUESTED, FRAUD_HOLD)  NULL
frozen_at            TIMESTAMPTZ                        NULL
frozen_by_admin_id   UUID FK -> users.id                NULL
```

`CardFreezeReason` lives in `cards/models.py` next to `CardStatus`.

## Behavior change in `cards/service.py`

- `freeze_card()` (cardholder self-service) now also sets
  `freeze_reason = USER_REQUESTED` and `frozen_at`.
- `unfreeze_card()` (cardholder self-service) now **refuses** with a 403
  (`AuthorizationError`) if `freeze_reason == FRAUD_HOLD`, message: *"Your
  card is frozen for security reasons. Please contact support."* A
  fraud-frozen card can only come back via the new admin action below — the
  cardholder can no longer unfreeze it themselves.
- Two new methods, both intended for cross-module use, not new HTTP routes on
  `cards/router.py`:
  - `freeze_for_fraud_hold(card_id)` — called by `FraudService` the moment a
    payment on that card crosses the fraud threshold. System-triggered, no
    acting user.
  - `activate_card_after_fraud_hold(card_id, admin_id)` — called by
    `FraudService.activate_card()`, itself behind the new admin-only
    `POST /fraud/cases/{id}/activate-card`. Requires
    `status == FROZEN and freeze_reason == FRAUD_HOLD`, else raises
    `ConflictError`.

None of this touches `create_card`, `delete_card`, PIN, payment preferences,
or the credit-card/collateral paths — if you're working on any of those,
nothing here should conflict.

## Why no temporary model

The earlier `Merchant`/`create_card_payment` pattern (a minimal stand-in
model + documented contract) was for a module that didn't exist yet —
`cards/` is fully built and owned by you, so forking a second `Card`-like
table would have created two sources of truth for the same entity instead of
one. I extended the real model with three nullable columns instead. If you'd
rather these fields live differently (e.g. a separate `card_freeze_events`
history table instead of flat columns on `Card`), that's an easy follow-up —
nothing downstream depends on the column layout, only on
`freeze_for_fraud_hold` / `activate_card_after_fraud_hold` existing on
`CardService` with their current signatures.

## Also touched

- `cards/schemas.py` — `CardPublic` gained `freeze_reason` and `frozen_at`
  (both optional, default `None`), so the frontend can tell a fraud hold
  apart from a self-freeze.
- Frontend `Card` type (`frontend/src/types/index.ts`) got the matching
  fields. `CardsPage.tsx` itself needed no changes — its existing
  `ApiError`-based error handling already surfaces whatever `detail` message
  the backend sends, so the 403 message above just shows up as-is.

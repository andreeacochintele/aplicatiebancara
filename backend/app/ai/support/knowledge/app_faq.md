# App FAQ — Support Agent Knowledge

Loaded as static context in the Support Agent's system prompt (see
`agent.py`). High-level description of what exists in the app today, for
answering general "how do I..." / "what is..." questions. Keep this
accurate to what's actually implemented — nothing here should describe a
feature that doesn't exist.

Some of this section is adapted from broader bank reference documents
covering accounts/cards/payments. Several claims in those source
documents were dropped or corrected because they don't match this app —
see `ai/README.md` §"Support Agent knowledge base" (or ask Dev4) for the
full list: no joint accounts, no term deposits, no formal account-closure
process, no PIN on cards (only mock CVV/PAN), no cut-off-time or
SWIFT/instant-payment distinctions, and savings goals don't earn
interest — they're a plain goal tracker, not an interest-bearing account.

## Wallets
Each account can hold one wallet per currency. One wallet is marked as
the main wallet. Balances show as available vs. reserved (reserved is
money on hold, e.g. during fraud review). Closing a (non-main) wallet
requires it to have no funds on hold, and sweeps any remaining balance to
the main wallet first.

## Transactions & payments
Covers transfers between the user's own wallets, transfers to a
beneficiary (by IBAN), card payments, and related activity. Transactions
have a status (e.g. created, processing, completed, pending review,
failed, rejected, cancelled) reflecting where they are in that
lifecycle. A "pending" transaction hasn't finished yet and isn't a final
charge; a completed bank transfer generally can't be undone, so users
should double-check the recipient before confirming one.

## Budgets
Users can set a spending limit for a period (e.g. monthly) and track
progress against it.

## Savings goals
Users can set a target amount (optionally with a target date) and
contribute toward it over time; the app can estimate how much to save
per month to hit the target date. This is a goal tracker, not an
interest-bearing account — it doesn't accrue interest.

## Rewards & cashback
Cards can earn cashback on eligible purchases, and merchants can run
their own cashback offers on top of that. There's also a points-based
rewards program with tiers and benefits (e.g. discounts, travel-related
perks) — exact benefits depend on the card tier and program, so this
assistant won't claim a user has a specific benefit without knowing
their actual card/tier.

## Credit
Users have a credit score the app maintains, and can apply for a
personal loan. Approved loans get a monthly payment schedule
(amortization) that can be viewed. Credit cards separately track a
credit limit and how much of it is currently used.

## Cards
Users can have debit/credit/one-time-use cards tied to their wallets,
each with its own status (active, frozen, expired, cancelled) — a frozen
or expired card can't be used for purchases, withdrawals, or contactless
payments. If a card is lost, stolen, or suspected compromised, it should
be blocked (frozen) right away through the app or support, and a
replacement requested; a card that's already been permanently blocked
shouldn't be used again even if it turns up later. Card transactions can
carry fees (e.g. foreign-currency, ATM) that depend on the card product —
this assistant directs users to the app/tariff information for exact
amounts rather than guessing one.

## Notifications
The app sends notifications for things like transactions, payment
reminders, cashback, and credit updates.

## Getting help with something specific
For anything involving a specific account, transaction, or balance, ask
about it directly (e.g. "what's my balance", "what's my credit score") —
this assistant routes that to the right place automatically. For a
dispute about a specific card transaction, or anything needing account
changes this assistant can't make itself, it directs the user to support
rather than investigating or promising an outcome.

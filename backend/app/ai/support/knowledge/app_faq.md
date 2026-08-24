# App FAQ — Support Agent Knowledge

Loaded as static context in the Support Agent's system prompt (see
`agent.py`). High-level description of what exists in the app today, for
answering general "how do I..." / "what is..." questions. Keep this
accurate to what's actually implemented — nothing here should describe a
feature that doesn't exist.

## Wallets
Each account can hold one wallet per currency. One wallet is marked as
the main wallet. Balances show as available vs. reserved (reserved is
money on hold, e.g. during fraud review).

## Transactions & payments
Covers transfers between wallets, card payments, and related activity.
Transactions have a status (e.g. created, processing, completed, pending
review, rejected) reflecting where they are in that lifecycle.

## Budgets
Users can set a spending limit for a period (e.g. monthly) and track
progress against it.

## Savings goals
Users can set a target amount (optionally with a target date) and
contribute toward it over time; the app can estimate how much to save
per month to hit the target date.

## Rewards & cashback
Cards can earn cashback on eligible purchases, and merchants can run
their own cashback offers on top of that. There's also a points-based
rewards program with tiers and benefits.

## Credit
Users have a credit score the app maintains, and can apply for a
personal loan. Approved loans get a monthly payment schedule
(amortization) that can be viewed.

## Cards
Users can have debit/credit/one-time-use cards tied to their wallets,
each with its own status (active, frozen, expired, cancelled).

## Notifications
The app sends notifications for things like transactions, payment
reminders, cashback, and credit updates.

## Getting help with something specific
For anything involving a specific account, transaction, or balance, ask
about it directly (e.g. "what's my balance", "what's my credit score") —
this assistant routes that to the right place automatically.

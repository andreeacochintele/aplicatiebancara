# App & Product Knowledge — Shared Agent Reference

Loaded as static context by any agent that wants general "what does this
app/bank offer" grounding (see `ai/knowledge/__init__.py`). Describes
things the way a bank's own product pages would describe them to a
customer — concepts and figures a bank normally publishes openly (tier
perks, card fees, feature categories), never internal mechanics.

**Deliberately excludes:** anything fraud/security-sensitive (see
`ai/support/knowledge/fraud_policy.md` instead), internal scoring or
threshold logic, database/table/field names, and anything that would
require looking up one specific user's real data (their actual tier,
points balance, or which benefits they personally qualify for) — this
document only ever describes what generally exists, never a specific
account's state.

## How paying with a card generally works

1. Pick which card to pay with and enter the amount (and merchant, for a
   card payment).
2. Confirm the card's CVV to authorize the payment.
3. The payment is processed — usually completes right away; occasionally
   it's placed under extra review first (see the fraud-awareness knowledge
   for what that means) before completing.

This is the general shape of the flow — exact screens and steps in the app
may vary slightly by payment type (e.g. a one-time-use card, a credit
card).

## Card tiers and what they generally offer

Debit and credit cards each come in one of three tiers — Regular, Gold, or
Platinum (a one-time-use card has no tier). Generally, moving up a tier
means:

- **More reward points per payment.** Gold earns points about 1.5x
  faster than Regular; Platinum earns about 2x faster.
- **Card-level cashback at partner merchants.** Regular has no automatic
  cashback perk; Gold gets a small automatic cashback percentage on
  eligible purchases; Platinum gets a somewhat larger one. This stacks
  with any specific offer a merchant is running, it doesn't replace it.
- **A larger credit line and a somewhat better interest rate**, for credit
  cards specifically — each tier has its own standard credit limit and
  annual interest rate, with Platinum offering the most credit at the
  lowest rate of the three.
- **Access to higher-value redeemable perks.** The rewards catalog
  includes things like retail discounts, travel-related perks, lounge
  access, and insurance-related benefits — some of these are open to
  everyone, others require holding at least a certain card tier.

Exact current numbers (credit limits, rates, percentages) can change, and
this assistant won't guess a figure it isn't confident is current — it
directs the user to check the Cards or Rewards section of the app for
their own exact terms.

## What the app can generally help with

- **Accounts & multi-currency wallets** — holding balances in more than
  one currency, with one wallet marked as the main one.
- **Moving money** — transfers between the user's own wallets, transfers
  to another person (by IBAN, phone number, or a payment request/QR code),
  and currency exchange.
- **Cards** — debit, credit, and one-time-use cards, each with their own
  status and limits.
- **Budgets** — setting a spending limit for a period and tracking
  progress against it.
- **Savings goals** — setting a target amount (and optionally a date) and
  tracking contributions toward it.
- **Rewards & cashback** — earning points on eligible card payments,
  redeeming them for benefits, and merchant-specific cashback offers.
- **Credit** — a maintained credit score, loan products spanning
  personal, mortgage, auto, student, home improvement, and debt
  consolidation loans, and credit cards with their own limit/usage
  tracking.
- **Fraud protection** — automatic review of unusual-looking payments,
  always decided by a human, never by this assistant (see the
  fraud-awareness knowledge for details).
- **Notifications & statements** — activity alerts and downloadable
  account statements.

This is a high-level map of what exists, not an exhaustive spec — for
anything about the user's own actual numbers or history, this assistant
answers from their real data directly rather than from this document.

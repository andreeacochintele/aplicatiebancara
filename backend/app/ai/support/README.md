# Support Agent (implemented — Phase 5)

Not one of the originally planned agents in architecture.md §29-32 —
added as a 5th orchestrator intent category (alongside personal_finance,
credit, greeting, out_of_scope) to hold general account/app help and
fraud-awareness questions that aren't personal_finance or credit. Routed
to from the Orchestrator for the `support` intent (`registry.py`).

## Files

```
knowledge/fraud_policy.md         -> qualitative-only fraud-pattern knowledge,
                                      based on fraud/service.py's real flag
                                      categories but rewritten with NO
                                      numbers/weights/windows, plus general
                                      (also number-free) phishing/device-
                                      security habits
knowledge/app_faq.md              -> high-level description of what the app
                                      actually has (wallets, transactions,
                                      budgets, savings, rewards, credit,
                                      cards, notifications)
knowledge/security_and_privacy.md -> identity verification, opening an
                                      account, personal data requests
agent.py                          -> handle(): loads all three files as
                                      static system-prompt context, then one
                                      azure_foundry_client call. No tools —
                                      see agent.py's own docstring for why.
                                      No `temperature=` kwarg (this
                                      deployment 400s on non-default values).
```

`app_faq.md` and `security_and_privacy.md` were expanded from 22 general
bank reference documents the user provided. Roughly a third of that
material was dropped or corrected — it described features this app
doesn't have (joint accounts, term deposits, formal account closure,
card PIN mechanics, transfer cut-off times, SWIFT/instant-payment
distinctions) or described a real feature wrongly (the source's "savings
account" earns interest; this app's savings goals don't). See each
knowledge file's own header for specifics.

## Zero financial-data access, by design

This agent never touches analytics/, budgets/, credit/, transactions/, or
fraud/ data — no tool exists here to call any of them. It:

- Explains fraud-awareness patterns qualitatively (see
  `knowledge/fraud_policy.md`'s own header for why no numbers are ever
  included).
- Never confirms or denies whether a specific transaction was flagged —
  it has no way to look one up, and its system prompt explicitly
  instructs it to redirect specific-case questions to support/an admin.
- Redirects real personal-finance/credit questions back to the user
  rather than guessing — normally the Orchestrator's intent classifier
  routes those away from this agent in the first place; this is a safety
  net for ambiguous phrasing that still lands here.

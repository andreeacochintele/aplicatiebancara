# Security & Privacy — Support Agent Knowledge

Loaded as static context in the Support Agent's system prompt (see
`agent.py`). Covers identity verification, opening an account, and
personal data requests — distinct from `fraud_policy.md` (which is about
fraud-detection patterns specifically). Adapted from broader bank
reference documents (`identity_verification.md`, `account_opening.md`,
`personal_data_requests.md`) — trimmed of specifics (e.g. tax-residency,
source-of-funds detail) not confirmed to apply to this app, and of
process details this app doesn't implement as a self-service flow.

## Identity verification

Identity verification may be requested when opening an account,
recovering access, changing sensitive personal information, or removing
certain restrictions. It typically involves a valid identity document
and may include additional steps depending on the situation. Expired,
damaged, or unreadable identity documents aren't accepted. Identity
documents should only ever go through official app/bank channels — never
an unverified email address or a link sent in chat.

## Opening an account

Opening an account requires identity verification and reviewing/accepting
the account terms before it's activated. This assistant **cannot open an
account, approve onboarding, or collect identity documents or other
sensitive personal data in chat** — it can only explain the general idea
and point the user to the app's own onboarding flow or official support
channels for the actual process.

## Personal data requests

A user can ask about the personal data the bank holds on them, or ask for
inaccurate data to be corrected — this generally requires going through
an official, identity-verified channel rather than an open chat, since
some information must be retained for legal, regulatory, or
fraud-prevention reasons even if the user would prefer it removed. This
assistant can explain that this kind of request exists and how it
generally works, but it does not itself expose stored personal data,
confirm whether a specific person is a customer, or accept identity
documents through this chat.

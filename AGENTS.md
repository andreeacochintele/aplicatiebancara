# AGENTS.md

## Purpose

This repository is developed in parallel by a team of 4 people using AI coding agents such as Codex and Claude.

The primary goal of these rules is to prevent agents from:

- overwriting another developer's work;
- making unrelated refactors;
- changing shared contracts without coordination;
- creating conflicting database migrations;
- implementing functionality outside the assigned task;
- coupling modules that are intended to remain independent;
- silently changing architecture decisions.

All coding agents must read this file before making changes.

---

# 1. Project architecture

The application is a banking web application implemented as a **modular monolith**.

Main stack:

- Frontend: React + TypeScript
- Backend: Python + FastAPI
- ORM: SQLAlchemy
- Migrations: Alembic
- Database: PostgreSQL
- Infrastructure: Docker / Docker Compose
- AI: Azure AI Foundry, GPT-5-mini only

The project architecture is documented in:

- `docs/architecture.md`
- `docs/architecture_diagrams.md`

These documents are the architectural source of truth.

Do not introduce a new architecture pattern without an explicit task requiring it.

---

# 2. Core architectural principles

The central banking domain is:

```text
User
  -> Wallet
  -> Transaction
  -> WalletLedgerEntry
```

Financial logic must remain deterministic.

AI agents must follow:

```text
AI Agent
  -> Tool
  -> Backend Service
  -> Database
```

AI agents must NEVER:

- access PostgreSQL directly;
- execute arbitrary SQL;
- bypass backend services;
- directly execute transfers or other sensitive financial actions;
- make final fraud or credit decisions by themselves.

Sensitive actions must be validated by deterministic backend logic and, where applicable, explicit user/admin confirmation.

---

# 3. Team parallel-development rule

Assume that other developers are modifying the repository at the same time.

Therefore:

1. Change only files required for the current task.
2. Do not perform repository-wide refactors unless explicitly requested.
3. Do not rename shared modules, folders, models, API routes, or database tables without explicit instruction.
4. Do not reformat unrelated files.
5. Do not "clean up" code outside the task scope.
6. Do not delete code that appears unused unless the task explicitly requires it.
7. Do not change another module's public behavior simply because a different design seems better.
8. Prefer additive changes over destructive changes.
9. Preserve backward compatibility whenever reasonable.
10. If a required change affects another module, minimize the change and clearly report it.

The smallest correct diff is preferred.

---

# 4. Branch policy

Each developer works on a dedicated feature branch.

Recommended branch structure:

```text
main
  feature/core-banking
  feature/payments
  feature/cards-credit
  feature/intelligence
```

Never assume the current branch belongs to you.

Before modifying code:

- inspect the current branch;
- inspect `git status`;
- inspect existing uncommitted changes;
- preserve changes that were already present.

Never run destructive Git commands unless explicitly requested.

Do NOT use commands such as:

```text
git reset --hard
git clean -fd
git checkout -- .
git restore .
git push --force
```

unless the user explicitly asks for them.

Never discard another developer's uncommitted work.

---

# 5. Module ownership

The repository is divided into logical work areas.

Typical ownership:

## Developer 1 - Core Banking

- wallets
- transactions
- ledger
- FX
- statements

## Developer 2 - Payments

- transfers
- phone transfers
- QR payments
- scheduled payments
- recurring payments
- split bill
- transaction folders
- business exports

## Developer 3 - Cards & Credit

- cards
- freeze/unfreeze
- one-time cards
- credit score
- loans
- loan calculator
- credit cards
- credit applications

## Developer 4 - Intelligence

- analytics
- budgets
- savings
- rewards
- merchant cashback
- fraud engine
- fraud admin workflow
- AI orchestrator
- personal finance agent
- credit agent
- fraud investigation agent

This ownership is guidance, not an authorization system.

When working on a task:

- stay within the relevant module whenever possible;
- avoid modifying another developer's module;
- if a shared change is required, keep it minimal.

---

# 6. Shared files are high-conflict files

Treat these files and areas as shared/high-conflict:

- `docker-compose.yml`
- `.env.example`
- root `README.md`
- global dependency files
- backend application entry point
- central router registration
- central configuration
- shared database base/models registry
- Alembic configuration
- frontend global router
- frontend global layout/navigation
- shared TypeScript types
- shared API client

Changes to shared files must be minimal and task-specific.

Do not reorder or rewrite entire shared files just to add one entry.

Example:

Bad:
- rewrite the full router file;
- rename all imports;
- reformat everything.

Good:
- add only the new router import and registration.

---

# 7. Database rules

Database changes are especially conflict-prone.

## 7.1 Models

Do not rename existing tables or columns unless explicitly required.

Do not change field meaning without updating all dependent services and schemas.

Use explicit SQLAlchemy relationships and foreign keys.

Financial amounts must use fixed precision decimal types, never floating point.

Use values such as:

```text
NUMERIC / DECIMAL
```

not `float` for money.

## 7.2 Alembic migrations

Never edit an already-shared migration just to add a new feature.

Create a new migration instead.

Before creating a migration:

1. inspect the current Alembic heads;
2. inspect recent migrations;
3. verify that your migration does not duplicate another developer's schema change.

If multiple Alembic heads exist because developers worked in parallel:

- do not silently rewrite migration history;
- create an Alembic merge migration when appropriate;
- clearly report that a merge migration was required.

Migration files should contain only changes relevant to the current feature.

Do not mix unrelated schema changes in one migration.

---

# 8. Transaction and ledger rules

`Transaction` and `WalletLedgerEntry` are core shared entities.

Treat changes to them as high risk.

Do not casually add feature-specific columns to the central transaction table when a dedicated related table would be cleaner.

Use the transaction lifecycle already defined by the project:

```text
CREATED
PROCESSING
PENDING_REVIEW
COMPLETED
FAILED
REJECTED
CANCELLED
```

Do not invent additional statuses without explicit architectural need.

Wallet balances and ledger entries must remain consistent.

Do not implement financial operations by only mutating `wallet.balance`.

Financial movements should be represented through the ledger according to the project's banking-core design.

Fraud holds should use reserved/held funds rather than pretending a suspicious transaction has completed.

---

# 9. API contract rules

Public API contracts are shared interfaces between team members.

Do not change an existing endpoint's:

- path;
- HTTP method;
- request body;
- response structure;
- status-code behavior;
- enum meaning;

unless the task explicitly requires a breaking change.

Prefer adding a new optional field over changing the meaning of an existing field.

All API routes should be versioned under:

```text
/api/v1
```

Keep route handlers thin.

Preferred flow:

```text
Route
  -> Service
  -> Repository / ORM
```

Business logic belongs in services, not route handlers.

---

# 10. Backend coding rules

Use:

- Python type hints;
- explicit Pydantic schemas;
- clear service boundaries;
- dependency injection where already established;
- small functions;
- meaningful names.

Avoid:

- giant service classes;
- hidden global state;
- circular imports;
- magic constants;
- duplicate business rules in multiple endpoints;
- catching broad exceptions without reason.

Follow existing repository conventions before introducing new patterns.

If the repository already has a pattern for routers/services/repositories, extend that pattern instead of inventing another one.

---

# 11. Frontend coding rules

Keep domain logic out of presentational components.

Prefer:

```text
page
  -> feature hook/service
  -> API client
```

Avoid direct hardcoded backend URLs inside components.

Use the shared API client/configuration.

Do not redesign unrelated screens when implementing one feature.

Do not change global styling or navigation unless the task specifically requires it.

Prefer reusable components only when there is actual reuse. Do not create abstractions prematurely.

Keep shared TypeScript types synchronized with backend API contracts.

---

# 12. Authentication and security rules

Never hardcode:

- passwords;
- API keys;
- JWT secrets;
- Azure credentials;
- database credentials.

Use environment variables.

Do not commit `.env` files containing secrets.

Only `.env.example` should contain placeholder values.

Passwords must be hashed.

Do not log passwords, access tokens, refresh tokens, biometric data, or sensitive financial information.

The inactivity timeout requirement is 5 minutes unless architecture changes explicitly.

Biometric verification is mock/sandbox functionality in this project.

Do not implement real biometric storage.

---

# 13. Azure AI / LLM rules

The only available LLM is:

```text
Azure AI Foundry
GPT-5-mini
```

Do not add integrations for:

- OpenAI direct API;
- Anthropic;
- Gemini;
- local models;
- alternate model providers;
- fallback model routing.

All AI functionality must reuse one shared Azure GPT-5-mini client abstraction.

Configuration must come from environment variables such as:

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_API_VERSION
AZURE_OPENAI_DEPLOYMENT_NAME
```

The application must remain runnable without Azure credentials when AI functionality is not being used.

Do not instantiate provider clients independently inside every agent.

---

# 14. AI agent rules

The planned agents are:

- Orchestrator Agent
- Personal Finance Agent
- Credit Agent
- Fraud Investigation Agent

The Orchestrator decides which specialized agent/tool should handle a request.

Agents may:

- retrieve data through approved tools;
- summarize;
- explain;
- analyze;
- recommend;
- prepare drafts;
- simulate scenarios.

Agents must not independently:

- execute money transfers;
- approve/reject loans;
- approve/reject fraud cases;
- freeze accounts without deterministic authorization;
- alter balances;
- alter ledger records directly.

Financial calculations such as:

- loan installments;
- outstanding principal;
- interest breakdown;
- early repayment;
- FX conversion;
- rewards calculation;
- fraud scoring;

must be performed by deterministic tools/services, not by LLM arithmetic or judgement.

---

# 15. Fraud rules

Separate:

```text
Fraud Engine
```

from:

```text
Fraud Investigation Agent
```

The Fraud Engine is deterministic and may assign a score/flags.

Suspicious transactions may enter:

```text
PENDING_REVIEW
```

The Fraud Investigation Agent may explain flags and summarize evidence.

Final approval/rejection belongs to the admin workflow.

Do not let the LLM make the final fraud decision.

---

# 16. Credit rules

Separate deterministic credit calculations from AI explanations.

Loan calculator functions should handle:

- monthly payment;
- remaining principal;
- payment breakdown;
- interest;
- amortization schedule;
- early repayment simulations;
- reducing period vs reducing installment.

The Credit Agent consumes these tool results and explains them.

Do not rely on the LLM to calculate financial schedules itself.

---

# 17. Mock/sandbox scope

This is a development/demo banking application.

Do not integrate real banking infrastructure unless explicitly requested.

The following should remain mock/sandbox unless requirements change:

- card generation;
- PAN/CVV;
- biometric checks;
- merchant network;
- banking rails;
- external settlements;
- credit bureau data;
- fraud providers.

Never store real card credentials.

---

# 18. Tests

Every feature should include relevant tests when practical.

At minimum, test:

- core business rules;
- validation;
- important error cases;
- permission checks;
- financial calculations.

Do not delete or weaken existing tests to make new code pass.

If an existing test is genuinely outdated because the requirement changed, explain why it must change.

Before finishing a task, run the smallest relevant test suite available.

If reasonable, also run the broader project test/build checks.

---

# 19. Dependencies

Do not add a dependency when the same functionality can reasonably be implemented with existing dependencies or the standard library.

Before adding a dependency:

- inspect existing dependency files;
- verify the project does not already contain an equivalent library;
- add it only to the correct backend/frontend dependency file.

Do not perform unrelated dependency upgrades.

Never upgrade major framework versions as part of an unrelated feature.

---

# 20. Formatting and style

Follow the existing formatter/linter configuration.

Do not introduce a new formatter or linter without explicit instruction.

Do not reformat unrelated files.

Comments should explain **why**, not restate obvious code.

Prefer readable code over clever code.

---

# 21. Before coding

For every non-trivial task, the agent should first:

1. Read this file.
2. Read the relevant architecture documentation.
3. Inspect the relevant existing modules.
4. Inspect `git status` and preserve existing changes.
5. Identify the smallest set of files that need modification.
6. Check whether the change touches a shared contract.
7. Check whether a database migration is actually required.

Do not start by generating a replacement architecture.

Work with the architecture that already exists.

---

# 22. During coding

While implementing:

- stay within task scope;
- make small coherent changes;
- reuse existing utilities;
- keep public interfaces stable;
- do not modify unrelated modules;
- avoid speculative features;
- avoid TODO-driven fake implementations unless placeholders are specifically requested.

If a placeholder is required, clearly mark what is intentionally not implemented.

---

# 23. Before finishing

Before declaring a task complete:

1. Review the diff.
2. Remove accidental unrelated changes.
3. Run relevant tests/build commands.
4. Check for migration conflicts if DB changes were made.
5. Check imports and API registration.
6. Verify no secrets were added.
7. Verify no existing behavior was silently broken.

Then report:

- what was changed;
- files changed;
- tests run;
- migrations added;
- shared contracts affected;
- anything another developer needs to know before merging.

---

# 24. Conflict-prevention checklist

Before editing a shared file, ask:

```text
Can this change be implemented inside my feature module instead?
```

Before editing a shared model, ask:

```text
Does this field truly belong in the shared model?
```

Before changing an API contract, ask:

```text
Will another developer's frontend/backend code depend on this contract?
```

Before changing architecture, ask:

```text
Was I explicitly asked to change architecture?
```

If the answer is no, prefer not to make the change.

---

# 25. Preferred merge-friendly behavior

Prefer:

- new files inside feature modules;
- small targeted edits;
- additive API changes;
- new migrations instead of rewriting old ones;
- feature-specific tests;
- local configuration additions instead of global rewrites.

Avoid:

- broad renames;
- moving folders;
- changing import style project-wide;
- reformatting the repository;
- rewriting central files;
- bundling multiple features into one task.

---

# 26. If architecture and code disagree

If current code and the architecture documentation disagree:

1. Do not silently rewrite everything.
2. Identify the mismatch.
3. Prefer the existing architecture document unless the user explicitly changed the requirement.
4. Make the smallest safe correction possible.
5. Report the mismatch clearly.

---

# 27. Final rule

When uncertain between:

```text
A larger cleaner refactor
```

and

```text
A smaller change that solves the assigned task without disturbing other developers
```

choose the **smaller merge-friendly change**.

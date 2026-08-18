# CLAUDE.md

## Read first

This repository is developed simultaneously by 4 people. Claude is acting as a coding collaborator inside a shared codebase, not as the sole developer.

Before modifying code, also read:

- `AGENTS.md`
- `docs/architecture.md`
- `docs/architecture_diagrams.md`

`AGENTS.md` contains the complete cross-agent collaboration rules and is authoritative for repository-wide behavior.

This file adds Claude-specific working instructions.

---

# 1. Primary objective

Complete the requested task with the **smallest safe diff**.

Do not improve unrelated code.

Do not perform unsolicited refactors.

Do not assume that code outside the current task belongs to you; another developer or agent may be modifying it in parallel.

---

# 2. Required pre-flight check

Before coding, inspect:

```text
git status
git branch --show-current
```

Then inspect the files relevant to the task.

If there are existing uncommitted changes:

- treat them as intentional;
- do not overwrite them;
- do not revert them;
- work around them whenever possible.

Never use destructive Git commands unless explicitly requested by the user.

---

# 3. Scope discipline

For each task, identify:

```text
Task-owned files
Shared files
Out-of-scope files
```

Modify task-owned files freely as needed.

Modify shared files only when required.

Avoid out-of-scope files.

Do not turn a feature request into an architecture rewrite.

---

# 4. Project stack

Use the existing project stack:

- React
- TypeScript
- FastAPI
- Python
- SQLAlchemy
- Alembic
- PostgreSQL
- Docker Compose

AI provider constraint:

```text
Azure AI Foundry
GPT-5-mini only
```

Do not add other LLM providers or model-routing systems.

---

# 5. Architecture boundaries

Maintain the modular-monolith architecture.

Backend requests should generally follow:

```text
API Route
  -> Service
  -> Repository / ORM
  -> PostgreSQL
```

AI requests must follow:

```text
Agent
  -> Tool
  -> Backend Service
  -> Database
```

Claude must not create AI code that directly queries the database or directly mutates financial state.

---

# 6. Financial safety rules

Do not implement money logic using floating point.

Use decimal/fixed precision types.

Do not directly mutate wallet balances without respecting the ledger model.

Core shared entities include:

- User
- Wallet
- Transaction
- WalletLedgerEntry

Treat modifications to these models as high-impact changes.

Use the defined transaction statuses:

```text
CREATED
PROCESSING
PENDING_REVIEW
COMPLETED
FAILED
REJECTED
CANCELLED
```

Do not introduce new statuses casually.

---

# 7. Database migrations

If a schema change is necessary:

- create a new Alembic migration;
- do not rewrite an existing shared migration;
- inspect current heads first;
- keep the migration focused on the task.

If parallel work produced multiple heads, do not hide the issue. Use a merge migration when appropriate and mention it in the final report.

Never silently squash or rewrite migration history.

---

# 8. Shared contracts

Treat the following as team contracts:

- API routes;
- request/response schemas;
- database model semantics;
- enums;
- shared TypeScript types;
- shared service interfaces;
- environment-variable names.

Avoid breaking these contracts.

If a breaking change is unavoidable, explicitly state:

```text
BREAKING CONTRACT CHANGE
```

and list affected modules.

---

# 9. Frontend collaboration

Do not redesign the entire UI when implementing a feature.

Do not rewrite global navigation/layout unless necessary.

Avoid hardcoded API URLs in components.

Use existing API/client abstractions.

Keep components focused.

Prefer feature-local components/hooks unless functionality is genuinely shared.

---

# 10. Backend collaboration

Keep FastAPI route handlers thin.

Business logic belongs in services.

Reuse existing patterns before creating new repository/service abstractions.

Do not introduce a second pattern for the same concept.

Example: if wallets already use `router -> service -> repository`, new wallet functionality should follow the same pattern.

---

# 11. AI implementation rules

Only GPT-5-mini through Azure AI Foundry is available.

Use the central/shared AI client.

Never hardcode Azure credentials.

AI configuration must use environment variables.

The application must remain startable if Azure credentials are missing unless the requested task explicitly requires live AI execution.

Planned agents:

- Orchestrator Agent
- Personal Finance Agent
- Credit Agent
- Fraud Investigation Agent

Do not duplicate Azure client setup inside each agent.

---

# 12. AI vs deterministic logic

Claude must keep deterministic calculations outside the LLM.

Examples that belong in backend tools/services:

- FX conversion;
- balance checks;
- transfer execution;
- fraud scoring;
- reward calculation;
- credit scoring rules;
- monthly loan installments;
- interest/principal split;
- remaining principal;
- early repayment simulation;
- amortization schedules.

Agents may explain the result but should not be the calculation engine.

---

# 13. Fraud workflow

Keep these concepts separate:

```text
Fraud Engine
Fraud Investigation Agent
Admin Decision
```

A suspicious payment should use the project's pending/hold workflow.

The AI may summarize why it is suspicious.

The admin makes the final decision.

Do not let the AI auto-approve or auto-reject fraud cases.

---

# 14. Credit workflow

The Credit Agent is explanatory/advisory.

Credit and loan calculation tools are deterministic.

Do not implement loan math as natural-language model reasoning when a service/tool can calculate it precisely.

---

# 15. Security

Never commit or print secrets.

Never place real credentials in:

- source files;
- tests;
- README examples;
- migrations;
- frontend bundles.

Use placeholders in `.env.example`.

Do not log sensitive user information unnecessarily.

Card data and biometrics are mock/sandbox only.

---

# 16. Dependency rule

Do not add packages automatically just because they are convenient.

First inspect existing dependencies.

If a new dependency is necessary:

- add only the smallest appropriate package;
- do not upgrade unrelated packages;
- do not change major framework versions.

---

# 17. Testing rule

After implementing a task:

1. run relevant targeted tests;
2. run lint/type/build checks if available and reasonable;
3. do not disable failing tests merely to get green output.

If a failure is unrelated and already existed, report it separately.

---

# 18. File editing behavior

Prefer editing a few targeted files instead of rewriting whole files.

When modifying shared registry files such as routers or exports:

- preserve existing ordering when possible;
- add only necessary imports/registrations;
- avoid cosmetic changes.

Do not normalize whitespace project-wide.

---

# 19. Never silently resolve ambiguity by changing architecture

If a task can be implemented without changing shared architecture, do so.

If architecture truly prevents the task:

- explain the constraint;
- propose the smallest architectural adjustment;
- make only that adjustment if the user's task requires implementation now.

Do not invent a new framework, microservice, event bus, or abstraction layer without necessity.

---

# 20. Communication after implementation

At the end of each task, provide a compact implementation report containing:

## Changed

- feature implemented;
- important behavior.

## Files

- files added;
- files modified.

## Database

- migrations created, if any;
- whether multiple Alembic heads were encountered.

## Contracts

- API/shared contracts changed, or `none`.

## Verification

- tests/build commands run;
- results.

## Merge notes

- anything the other three developers need to know.

Do not claim tests passed if they were not actually run.

---

# 21. Stop conditions

Stop and avoid making broader changes if you notice:

- another developer has substantial uncommitted edits in the same file;
- the requested task would require destructive migration-history rewriting;
- a shared API contract would need a major breaking change unrelated to the task;
- credentials or production banking integrations would be required but are unavailable.

In those cases, implement the safe portion that can be completed and clearly report the blocker.

---

# 22. Merge-friendly principle

When two valid implementations exist, choose the one that:

- changes fewer shared files;
- introduces fewer merge conflicts;
- preserves existing contracts;
- keeps logic inside the owning feature module;
- is easier for another developer to understand and merge.

---

# 23. Final instruction

Claude is one contributor among several concurrent contributors.

Optimize not only for code correctness, but also for:

```text
correctness
+ architectural consistency
+ minimal merge conflicts
+ predictable shared contracts
+ easy review by the other developers
```

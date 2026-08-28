# AI module

Phase 5 (Agentic AI). The Orchestrator and all four registered agents
(Personal Finance, Credit, Support, Actions) are implemented. Fraud is
untouched/out of scope for the orchestrator.

The first three agents are read-only (they explain data). **Actions**
(`actions/`) is the first to prepare a state-changing operation — a
phone/name transfer — via the draft → confirm → execute flow from rule 3
below: one strict-JSON extraction call, then fully deterministic
(recipient resolved against the user's own beneficiaries, 500 RON cap,
balance check, light fraud screen). `POST /ai/actions/{id}/confirm`
re-validates from the stored draft and reuses
`TransactionService.create_internal_transfer` — the chat message never
carries authority. Follow-up not in this pass: routing agent transfers
through the full fraud engine (its HOLD/approve path is card-payment-only
today).

## Constraint: single model, single provider

The only LLM available to this project is **GPT-5-mini deployed on Azure AI
Foundry**. Do not add:

- direct OpenAI API integrations
- Anthropic, Gemini, or local-model integrations
- fallback models or multi-model routing
- model comparison logic
- dependencies for AI providers other than Azure OpenAI/Azure AI Foundry

All future agents call [`ai/client/azure_foundry_client.py`](client/azure_foundry_client.py)
— never instantiate a model client directly in an agent.

## Layout

```
ai/
├── client/           # shared Azure AI Foundry GPT-5-mini client (implemented)
├── orchestrator/      # intent routing (single-agent routing only)
├── personal_finance/  # implemented — spending/budgets/savings/cashback/forecast
├── credit/             # implemented — score/loans/payment/principal/early-repayment (approx.)
├── support/            # implemented — app FAQ + qualitative fraud awareness, no tools/data access
│   └── knowledge/       # static .md files loaded into the system prompt (not tool-called)
├── actions/            # implemented — prepares a phone/name transfer (draft → confirm → execute),
│                        #   AgentAction table, confirm/cancel routes, light pre-execution fraud screen
├── fraud/               # future: fraud case investigation support (untouched, out of scope)
└── tools/              # base.py: shared ToolContext/ToolDataUnavailableError contract —
                        # each agent's own tools.py wraps that agent's backend services
```

## Watching the orchestration flow live

Every chat request logs one line per step — request received, intent
classified, agent dispatched, each tool call, each LLM call, final
response — tagged with a short per-request `correlation_id` (see
`observability.py`). Format is a single grep-friendly line, not JSON:

```
[a1b2c3d4] event=request_received user_id=8cd73020… message_length=42
[a1b2c3d4] event=intent_classified intent=personal_finance confidence=n/a
[a1b2c3d4] event=agent_dispatched agent=personal_finance intent=personal_finance
[a1b2c3d4] event=tool_call tool=get_wallet_balances duration_ms=4.1 status=ok
[a1b2c3d4] event=llm_call agent=personal_finance duration_ms=612.3 status=ok
[a1b2c3d4] event=final_response intent=personal_finance duration_ms=618.9
```

Watch it live while testing manually from the UI:

```bash
docker compose logs backend -f
```

Isolate one conversation — the `correlation_id` is also returned in the
chat response body (`OrchestratorChatResponse.correlation_id`), so you can
copy it from there (or from the log line itself) and filter:

```bash
docker compose logs backend -f | grep a1b2c3d4          # bash
docker compose logs backend -f | Select-String a1b2c3d4  # PowerShell
```

Filter by event type across all conversations the same way, e.g.
`grep event=tool_call` or `Select-String "event=tool_call"`.

Full LLM prompt/response bodies are logged separately at DEBUG (not INFO,
since they're verbose) — set `AI_LOG_LEVEL=DEBUG` in the environment to
see them; default is INFO.

`confidence=n/a` on `intent_classified` isn't a bug — `classify_intent()`
only returns a category today, no confidence score, so this is logged
honestly rather than inventing one.

## Non-negotiable rules (architecture.md §28, §33, §44)

1. **Agents never access the database directly.** Flow is always
   `Agent -> Tool -> Backend Service -> Database`.
2. **Deterministic financial logic stays in backend services**, not in the
   LLM: balances, FX rates, credit score, interest, fraud score, cashback.
3. **Write/financial actions require explicit user confirmation.** Agents may
   create drafts (e.g. `create_transfer_draft()`); only the backend executes
   the real operation (`execute_transfer()`), and only after the user
   confirms in the UI.
4. **Fraud Investigation Agent recommends, admin decides.** The agent never
   auto-approves or auto-rejects a fraud case.

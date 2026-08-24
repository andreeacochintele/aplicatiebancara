import uuid

import pytest

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.support import agent

# fraud/service.py's real, non-public constants — the exact values that must
# never leak into the Support Agent's knowledge/system prompt. Importing them
# (rather than hardcoding "25"/"30"/etc. here) means this test automatically
# stays in sync if Dev4's own fraud engine tuning changes these numbers later.
from app.fraud.service import (
    FRAUD_SCORE_THRESHOLD,
    HIGH_AMOUNT_MULTIPLIER,
    HIGH_AMOUNT_MIN_HISTORY,
    HIGH_VELOCITY_MIN_COUNT,
    HIGH_VELOCITY_WINDOW,
    NEW_DEVICE_POINTS,
    REWARD_ABUSE_MIN_COUNT,
    REWARD_ABUSE_WINDOW,
    UNUSUAL_COUNTRY_POINTS,
    HIGH_AMOUNT_POINTS,
    REWARD_ABUSE_PATTERN_POINTS,
    HIGH_VELOCITY_POINTS,
)

_REAL_FRAUD_NUMBERS = {
    str(FRAUD_SCORE_THRESHOLD),
    str(NEW_DEVICE_POINTS),
    str(HIGH_AMOUNT_POINTS),
    str(UNUSUAL_COUNTRY_POINTS),
    str(REWARD_ABUSE_PATTERN_POINTS),
    str(HIGH_VELOCITY_POINTS),
    str(HIGH_AMOUNT_MULTIPLIER),
    str(HIGH_AMOUNT_MIN_HISTORY),
    str(HIGH_VELOCITY_MIN_COUNT),
    str(REWARD_ABUSE_MIN_COUNT),
    str(HIGH_VELOCITY_WINDOW.seconds // 60),
    str(REWARD_ABUSE_WINDOW.seconds // 60),
}


# ---- fraud-awareness question: no numeric/threshold leakage in the source knowledge ----


def test_fraud_policy_knowledge_contains_no_digits_at_all():
    # Strongest possible check: the qualitative rewrite shouldn't need a
    # single digit anywhere, so any digit at all is worth investigating.
    assert not any(char.isdigit() for char in agent._FRAUD_POLICY)


def test_fraud_policy_knowledge_does_not_contain_any_real_fraud_engine_number():
    for number in _REAL_FRAUD_NUMBERS:
        assert number not in agent._FRAUD_POLICY


def test_system_prompt_includes_both_knowledge_files_verbatim():
    assert agent._FRAUD_POLICY in agent._SYSTEM_PROMPT
    assert agent._APP_FAQ in agent._SYSTEM_PROMPT


def test_system_prompt_forbids_numeric_fraud_details_and_specific_case_confirmation():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "never state numeric thresholds" in lowered
    assert "never" in lowered and "confirm or deny" in lowered
    assert "contact support" in lowered or "admin" in lowered


# ---- redirect case: the prompt tells the model to defer real financial-data questions ----


def test_system_prompt_instructs_redirecting_real_financial_data_questions():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "no access to any user's real financial data" in lowered
    assert "ask" in lowered  # tells the model to point the user to ask directly


# ---- agent.py plumbing: mocked at the LLM boundary, never a live Azure call ----


def test_handle_is_a_thin_passthrough_to_explain(db_session, monkeypatch):
    captured = {}

    def _fake_explain(message: str, history: list[dict[str, str]] | None = None) -> str:
        captured["message"] = message
        return "Mocked support reply."

    monkeypatch.setattr(agent, "_explain", _fake_explain)

    reply = agent.handle("how do budgets work?", uuid.uuid4(), db_session)

    assert reply == "Mocked support reply."
    assert captured["message"] == "how do budgets work?"


def test_handle_propagates_azure_not_configured_from_explain(db_session, monkeypatch):
    def _raise_not_configured(message: str, history: list[dict[str, str]] | None = None) -> str:
        raise AzureFoundryNotConfiguredError("Azure AI Foundry is not configured.")

    monkeypatch.setattr(agent, "_explain", _raise_not_configured)

    with pytest.raises(AzureFoundryNotConfiguredError):
        agent.handle("is a payment from a new device risky?", uuid.uuid4(), db_session)


# ---- proactive-answering fix: a clearly-scoped question should be answered
# directly rather than met with "which topic did you mean?". Whether a real
# model actually stops hedging can't be asserted from a mocked test (support
# has no tools/dispatch to check either — see agent.py's module docstring)
# — that's what the live smoke test in the task report covers; this protects
# the fix itself from being silently removed from the prompt.


def test_system_prompt_instructs_answering_directly_without_asking_which_topic():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "be direct" in lowered
    assert "don't ask which topic they meant" in lowered


def test_system_prompt_still_allows_clarifying_questions_when_genuinely_ambiguous():
    lowered = agent._SYSTEM_PROMPT.lower()
    assert "genuinely ambiguous between multiple different topics" in lowered

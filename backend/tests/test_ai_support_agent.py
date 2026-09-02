import uuid

import pytest

from app.ai.client.azure_foundry_client import AzureFoundryNotConfiguredError
from app.ai.guardrails import INJECTION_GUARDRAILS, RESPONSE_FORMAT_RULE
from app.ai.support import agent

# fraud/service.py's real, non-public constants — the exact values that must
# never leak into the Support Agent's knowledge/system prompt. Importing them
# (rather than hardcoding "25"/"30"/etc. here) means this test automatically
# stays in sync if Dev4's own fraud engine tuning changes these numbers later.
from app.fraud.service import (
    FRAUD_SCORE_THRESHOLD,
    HIGH_AMOUNT_MULTIPLIER,
    HIGH_AMOUNT_MIN_HISTORY,
    HIGH_AMOUNT_BASE_POINTS,
    HIGH_AMOUNT_POINTS_PER_EXTRA_MULTIPLE,
    HIGH_AMOUNT_MAX_POINTS,
    HIGH_VELOCITY_MIN_COUNT,
    HIGH_VELOCITY_WINDOW,
    HIGH_VELOCITY_BASE_POINTS,
    HIGH_VELOCITY_POINTS_PER_EXTRA,
    HIGH_VELOCITY_MAX_POINTS,
    NEW_DEVICE_POINTS,
    REWARD_ABUSE_MIN_COUNT,
    REWARD_ABUSE_WINDOW,
    REWARD_ABUSE_BASE_POINTS,
    REWARD_ABUSE_POINTS_PER_EXTRA,
    REWARD_ABUSE_MAX_POINTS,
    UNUSUAL_COUNTRY_POINTS,
    UNUSUAL_TIME_POINTS,
    UNUSUAL_TIME_WINDOW_START_HOUR,
    UNUSUAL_TIME_WINDOW_END_HOUR,
    MULTI_FLAG_BONUS_PER_EXTRA_FLAG,
    MULTI_FLAG_BONUS_MAX,
)

_REAL_FRAUD_NUMBERS = {
    str(FRAUD_SCORE_THRESHOLD),
    str(NEW_DEVICE_POINTS),
    str(UNUSUAL_COUNTRY_POINTS),
    str(HIGH_AMOUNT_BASE_POINTS),
    str(HIGH_AMOUNT_POINTS_PER_EXTRA_MULTIPLE),
    str(HIGH_AMOUNT_MAX_POINTS),
    str(HIGH_VELOCITY_BASE_POINTS),
    str(HIGH_VELOCITY_POINTS_PER_EXTRA),
    str(HIGH_VELOCITY_MAX_POINTS),
    str(REWARD_ABUSE_BASE_POINTS),
    str(REWARD_ABUSE_POINTS_PER_EXTRA),
    str(REWARD_ABUSE_MAX_POINTS),
    str(UNUSUAL_TIME_POINTS),
    str(UNUSUAL_TIME_WINDOW_START_HOUR),
    str(UNUSUAL_TIME_WINDOW_END_HOUR),
    str(MULTI_FLAG_BONUS_PER_EXTRA_FLAG),
    str(MULTI_FLAG_BONUS_MAX),
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


def test_system_prompt_includes_all_knowledge_files_verbatim():
    for prompt in agent._SYSTEM_PROMPTS.values():
        assert agent._FRAUD_POLICY in prompt
        assert agent._APP_FAQ in prompt
        assert agent._SECURITY_AND_PRIVACY in prompt
        assert agent._APP_OVERVIEW in prompt


# ---- shared ai/knowledge/app_overview.md: same qualitative/no-leakage bar
# as the fraud knowledge above, since it's shared with Personal Finance too ----


def test_app_overview_knowledge_does_not_contain_the_fraud_score_threshold():
    # Unlike fraud_policy.md (held to a strict zero-digits bar — small
    # numbers are expected here for legitimate reasons, e.g. tier point
    # multipliers and step numbering), so this checks specifically for the
    # one number that would matter if it leaked: the deterministic fraud
    # engine's actual pass/fail threshold, not every generic small integer
    # a fraud constant happens to also equal.
    assert str(FRAUD_SCORE_THRESHOLD) not in agent._APP_OVERVIEW


def test_app_overview_knowledge_has_no_internal_implementation_detail():
    lowered = agent._APP_OVERVIEW.lower()
    for leaky_term in (
        "sqlalchemy", "postgres", "fraud_cases", "fraud_score",
        "card_freeze_reason", "risk_score", "azure", "gpt-5",
    ):
        assert leaky_term not in lowered


# ---- shared ai/guardrails.py: injection resistance + response-format rule ----


def test_system_prompt_includes_the_shared_injection_and_format_guardrails():
    for prompt in agent._SYSTEM_PROMPTS.values():
        assert INJECTION_GUARDRAILS in prompt
        assert RESPONSE_FORMAT_RULE in prompt


def test_system_prompt_forbids_numeric_fraud_details_and_specific_case_confirmation():
    for prompt in agent._SYSTEM_PROMPTS.values():
        lowered = prompt.lower()
        assert "never state numeric thresholds" in lowered
        assert "never" in lowered and "confirm or deny" in lowered
        assert "contact support" in lowered or "admin" in lowered


def test_system_prompt_forbids_reconstructing_internal_logic_from_conversation():
    for prompt in agent._SYSTEM_PROMPTS.values():
        lowered = prompt.lower()
        assert "never reconstruct or paraphrase" in lowered
        assert "pasted by the user" in lowered


# ---- routing gap fix: intent.py routes conceptual "how is X calculated"
# questions to Support (same pattern as fraud), so a general credit-score
# question never reaches the Credit Agent's own knowledge base — Support
# needs its own grounding for this or it falls back to (wrong, for this
# app) general knowledge about credit bureaus.


def test_system_prompt_includes_credit_score_factors_knowledge_verbatim():
    for prompt in agent._SYSTEM_PROMPTS.values():
        assert agent._CREDIT_SCORE_FACTORS in prompt


def test_credit_score_factors_knowledge_contains_no_digits():
    assert not any(char.isdigit() for char in agent._CREDIT_SCORE_FACTORS)


def test_system_prompt_forbids_outside_general_knowledge_about_credit_scoring():
    for prompt in agent._SYSTEM_PROMPTS.values():
        assert "never invent or use outside/general knowledge about" in prompt.lower()


# ---- redirect case: the prompt tells the model to defer real financial-data questions ----


def test_system_prompt_instructs_redirecting_real_financial_data_questions():
    for prompt in agent._SYSTEM_PROMPTS.values():
        lowered = prompt.lower()
        assert "no access to any user's real financial data" in lowered
        assert "ask" in lowered  # tells the model to point the user to ask directly


# ---- agent.py plumbing: mocked at the LLM boundary, never a live Azure call ----


def test_handle_is_a_thin_passthrough_to_explain(db_session, monkeypatch):
    captured = {}

    def _fake_explain(message: str, history: list[dict[str, str]] | None = None, locale: str = "ro") -> str:
        captured["message"] = message
        return "Mocked support reply."

    monkeypatch.setattr(agent, "_explain", _fake_explain)

    reply = agent.handle("how do budgets work?", uuid.uuid4(), db_session)

    assert reply == "Mocked support reply."
    assert captured["message"] == "how do budgets work?"


def test_handle_propagates_azure_not_configured_from_explain(db_session, monkeypatch):
    def _raise_not_configured(message: str, history: list[dict[str, str]] | None = None, locale: str = "ro") -> str:
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
    for prompt in agent._SYSTEM_PROMPTS.values():
        lowered = prompt.lower()
        assert "be direct" in lowered
        assert "don't ask which topic they meant" in lowered


def test_system_prompt_still_allows_clarifying_questions_when_genuinely_ambiguous():
    for prompt in agent._SYSTEM_PROMPTS.values():
        assert "genuinely ambiguous between multiple different topics" in prompt.lower()


def test_system_prompt_instructs_a_definitive_target_language_per_locale():
    # Locale now comes from the site's own language setting (X-Locale
    # header, see ai/locale.py) rather than being guessed from the
    # message text, so each locale variant gets a direct instruction.
    assert "always respond in romanian" in agent._SYSTEM_PROMPTS["ro"].lower()
    assert "always respond in english" in agent._SYSTEM_PROMPTS["en"].lower()


# ---- knowledge base curated from 22 user-provided bank reference docs: about
# a third described features this app doesn't have, or described a real
# feature incorrectly. These tests guard the corrections/omissions rather
# than assuming the source material was accurate.


def test_app_faq_does_not_claim_savings_goals_earn_interest():
    # The source doc described an interest-bearing "savings account";
    # this app's savings goals are a plain tracker with no interest.
    lowered = agent._APP_FAQ.lower()
    assert "doesn't accrue interest" in lowered or "does not accrue interest" in lowered
    assert "earns interest" not in lowered and "earn interest" not in lowered


def test_app_faq_does_not_describe_features_this_app_lacks():
    # The file's own header legitimately names these (to explain what was
    # excluded and why) — check only the content sections after it, so this
    # test fails if one were ever actually *described* there, not merely
    # mentioned as "we dropped this".
    content_body = agent._APP_FAQ.split("## Wallets", 1)[1].lower()
    for absent_feature in ("joint account", "term deposit", "swift", "cut-off"):
        assert absent_feature not in content_body


def test_security_and_privacy_forbids_collecting_sensitive_data_in_chat():
    # Normalize the markdown's line-wrapping so a phrase isn't missed just
    # because a `\n` happens to fall inside it.
    flat = " ".join(agent._SECURITY_AND_PRIVACY.lower().split())
    assert "cannot open an account" in flat
    assert "collect identity documents" in flat

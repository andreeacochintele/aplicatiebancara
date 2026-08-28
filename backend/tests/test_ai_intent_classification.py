"""Regression tests for the personal_finance-vs-support misclassification
fixed in intent.py's system prompt (live-confirmed via structured logging:
"What is my wallet balance?" was landing on support, "How do budgets work
in this app?" was landing on personal_finance — both backwards).

Two layers, since neither alone proves the fix:
- Content assertions on _SYSTEM_PROMPT: catch someone later deleting the
  few-shot examples/heuristic that fix this, even though they can't prove
  a real model follows them.
- classify_intent() with the Azure client mocked to return the *correct*
  category: proves the classification pipeline (prompt construction ->
  chat_completion call -> _parse_category) doesn't mangle a correct model
  answer for these exact messages. Neither test is a substitute for a
  live call against the real model — that's the separate live smoke test
  in the task report, not something CI can assert on.
"""
import pytest

from app.ai.orchestrator import intent
from app.ai.orchestrator.intent import IntentCategory, classify_intent


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    def __init__(self, content: str) -> None:
        self._content = content

    def chat_completion(self, **kwargs) -> _FakeResponse:
        self.last_kwargs = kwargs
        return _FakeResponse(self._content)


# ---- the two live-confirmed misclassifications, as exact regression examples ----


def test_system_prompt_contains_the_two_originally_misclassified_examples_corrected():
    assert "'What is my wallet balance?' -> personal_finance" in intent._SYSTEM_PROMPT
    assert "'How do budgets work in this app?' -> support" in intent._SYSTEM_PROMPT


def test_system_prompt_contains_the_additional_ambiguous_pairs():
    assert "'How does savings work?' -> support" in intent._SYSTEM_PROMPT
    assert "'How much do I have saved?' -> personal_finance" in intent._SYSTEM_PROMPT
    assert "'What's a cashback offer?' -> support" in intent._SYSTEM_PROMPT
    assert "'Do I have any cashback right now?' -> personal_finance" in intent._SYSTEM_PROMPT
    assert "'What counts as a transaction?' -> support" in intent._SYSTEM_PROMPT
    assert "'Show me my recent transactions' -> personal_finance" in intent._SYSTEM_PROMPT


def test_system_prompt_contains_the_data_vs_how_it_works_heuristic():
    lowered = intent._SYSTEM_PROMPT.lower()
    assert "asks for the user's actual current data/numbers, classify personal_finance" in lowered
    assert "asks how something works" in lowered and "classify support" in lowered


@pytest.mark.parametrize(
    "message, model_reply, expected",
    [
        ("What is my wallet balance?", "personal_finance", IntentCategory.PERSONAL_FINANCE),
        ("How do budgets work in this app?", "support", IntentCategory.SUPPORT),
        ("How does savings work?", "support", IntentCategory.SUPPORT),
        ("How much do I have saved?", "personal_finance", IntentCategory.PERSONAL_FINANCE),
        ("What's a cashback offer?", "support", IntentCategory.SUPPORT),
        ("Do I have any cashback right now?", "personal_finance", IntentCategory.PERSONAL_FINANCE),
        ("What counts as a transaction?", "support", IntentCategory.SUPPORT),
        ("Show me my recent transactions", "personal_finance", IntentCategory.PERSONAL_FINANCE),
    ],
)
def test_classify_intent_returns_the_correct_category_when_the_model_answers_correctly(
    monkeypatch, message, model_reply, expected
):
    monkeypatch.setattr(intent, "get_azure_foundry_client", lambda: _FakeClient(model_reply))
    assert classify_intent(message) == expected


# ---- Romanian support: live-found while investigating a report — messages in
# Romanian ("Ce sold am?") were falling through to support/out_of_scope
# instead of personal_finance, since the prompt had no Romanian examples at
# all and _parse_category defaulted an unrecognized reply to out_of_scope. ----


def test_system_prompt_says_to_classify_romanian_by_meaning():
    lowered = intent._SYSTEM_PROMPT.lower()
    assert "romanian" in lowered
    assert "classify by meaning" in lowered


def test_system_prompt_contains_the_romanian_examples():
    assert "'Ce sold am?' -> personal_finance" in intent._SYSTEM_PROMPT
    assert "'Cat am in cont?' -> personal_finance" in intent._SYSTEM_PROMPT
    assert "'Cum functioneaza bugetele?' -> support" in intent._SYSTEM_PROMPT
    assert "'Arata-mi cheltuielile din ultima luna' -> personal_finance" in intent._SYSTEM_PROMPT


@pytest.mark.parametrize(
    "message, model_reply, expected",
    [
        ("Ce sold am?", "personal_finance", IntentCategory.PERSONAL_FINANCE),
        ("Cat am in cont?", "personal_finance", IntentCategory.PERSONAL_FINANCE),
        ("Cum functioneaza bugetele?", "support", IntentCategory.SUPPORT),
        ("Arata-mi cheltuielile din ultima luna", "personal_finance", IntentCategory.PERSONAL_FINANCE),
    ],
)
def test_classify_intent_returns_the_correct_category_for_romanian_messages(
    monkeypatch, message, model_reply, expected
):
    monkeypatch.setattr(intent, "get_azure_foundry_client", lambda: _FakeClient(model_reply))
    assert classify_intent(message) == expected


def test_parse_category_defaults_to_support_on_unrecognized_reply():
    assert intent._parse_category("hmm, not sure") == IntentCategory.SUPPORT


# ---- personal_finance-vs-credit misclassification, live-confirmed via a
# broad manual test sweep: "Tell me about my loans" and "What's my monthly
# payment?" were landing on personal_finance (which has no keyword for loans
# and silently falls back to its default wallet_balances tool, giving the
# user an unrelated wallet-balance dump instead of their loan data), and
# several other loan-shaped questions drifted to support/personal_finance
# over a longer conversation. Same two-layer pattern as the
# personal_finance-vs-support fix above.


def test_system_prompt_contains_the_personal_finance_vs_credit_heuristic():
    lowered = intent._SYSTEM_PROMPT.lower()
    assert "personal_finance vs credit is the other common mix-up" in lowered
    assert "does not include loans or credit score" in lowered


def test_system_prompt_contains_the_loan_examples_corrected_to_credit():
    assert "'Tell me about my loans' -> credit" in intent._SYSTEM_PROMPT
    assert "'What's my monthly payment?' -> credit" in intent._SYSTEM_PROMPT
    assert "'How much do I still owe?' -> credit" in intent._SYSTEM_PROMPT
    assert "'Do I have any pending loan applications?' -> credit" in intent._SYSTEM_PROMPT
    assert "'Can I pay off my loan early?' -> credit" in intent._SYSTEM_PROMPT


@pytest.mark.parametrize(
    "message, model_reply, expected",
    [
        ("Tell me about my loans", "credit", IntentCategory.CREDIT),
        ("What's my monthly payment?", "credit", IntentCategory.CREDIT),
        ("How much do I still owe?", "credit", IntentCategory.CREDIT),
        ("Do I have any pending loan applications?", "credit", IntentCategory.CREDIT),
        ("Can I pay off my loan early?", "credit", IntentCategory.CREDIT),
    ],
)
def test_classify_intent_returns_credit_for_own_loan_data_questions(monkeypatch, message, model_reply, expected):
    monkeypatch.setattr(intent, "get_azure_foundry_client", lambda: _FakeClient(model_reply))
    assert classify_intent(message) == expected


# ---- latency fix: reasoning_effort="minimal" on classify_intent's own call only ----
#
# Live-verified separately (task report, not asserted here — no live Azure
# calls in the suite): accepted by this deployment with no error (unlike
# temperature), ~32% average latency reduction across the 4 canonical test
# questions, and no accuracy change across every case in this file. This
# test protects the plumbing: the parameter is actually sent, and it never
# leaks into an agent's response-generation call (checked by grep over
# backend/app in the task report - reasoning_effort appears only here).


def test_classify_intent_passes_reasoning_effort_minimal(monkeypatch):
    fake = _FakeClient("support")
    monkeypatch.setattr(intent, "get_azure_foundry_client", lambda: fake)

    classify_intent("how do budgets work?")

    assert fake.last_kwargs["reasoning_effort"] == "minimal"

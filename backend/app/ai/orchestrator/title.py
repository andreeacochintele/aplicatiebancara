"""Conversation title generation — one cheap GPT-5-mini call the first time
a conversation gets its first (question, answer) pair, so the sidebar shows
a real title instead of the raw first message. Triggered from
OrchestratorService.chat(), guarded by `Conversation.title is None` so it
only ever runs once per conversation — see that method for the call site
and the best-effort failure handling (a failed/unavailable title generation
must never break the chat reply that was already computed and persisted).
"""
from app.ai.client.azure_foundry_client import get_azure_foundry_client
from app.ai.observability import timed_event

_SYSTEM_PROMPT = (
    "Generate a concise 3-5 word title summarizing what this conversation is "
    "about, in the same language as the conversation. Reply with only the "
    "title itself — no quotes, no punctuation at the end, nothing else."
)

_MAX_TITLE_LENGTH = 80  # defensive cap — column is String(255), title.py just keeps it short


def generate_conversation_title(user_message: str, reply: str) -> str:
    """One cheap call through the shared client, same pattern as
    intent.py's classifier — reasoning_effort="minimal" since summarizing
    a single exchange into a few words needs no deep reasoning."""
    client = get_azure_foundry_client()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"User: {user_message}\nAssistant: {reply}"},
    ]
    with timed_event("llm_call", agent="orchestrator_title"):
        response = client.chat_completion(messages=messages, reasoning_effort="minimal")
    return _clean_title(response.choices[0].message.content)


def _clean_title(raw: str) -> str:
    """Defensive cleanup in case the model doesn't follow the "no quotes, no
    trailing punctuation" instruction exactly — same spirit as
    ai/fraud/agent.py's _parse_reply parsing its own model output."""
    title = raw.strip().strip('"').strip("'").rstrip(".!?").strip()
    return title[:_MAX_TITLE_LENGTH]

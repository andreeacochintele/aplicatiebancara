import { useEffect, useRef, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type {
  ConversationMessagePublic,
  ConversationPublic,
  ConversationSummary,
  OrchestratorChatResponse,
  OrchestratorIntent,
} from "../types";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  intent?: OrchestratorIntent;
}

const INTENT_LABEL: Record<OrchestratorIntent, string> = {
  personal_finance: "Personal finance",
  credit: "Credit",
  support: "Support",
  greeting: "Greeting",
  out_of_scope: "Out of scope",
};

const MESSAGES_PAGE_SIZE = 50;

function toChatMessage(entry: ConversationMessagePublic): ChatMessage {
  return {
    role: entry.role === "assistant" ? "assistant" : "user",
    text: entry.content,
    intent: entry.agent_used ?? undefined,
  };
}

export function AssistantPage() {
  const { accessToken } = useAuth();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [oldestLoadedCreatedAt, setOldestLoadedCreatedAt] = useState<string | null>(null);
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const shouldScrollToBottomRef = useRef(false);

  // ---- conversation list (sidebar) ----

  async function refreshConversations() {
    if (!accessToken) return;
    try {
      const list = await apiRequest<ConversationSummary[]>("/ai/orchestrator/conversations", { token: accessToken });
      setConversations(list);
      return list;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load conversations");
      return [];
    }
  }

  // On mount: load the conversation list, then open the most recently
  // updated one if any exist (so reopening the page resumes where the user
  // left off) — otherwise leave a blank slate until they send a message.
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;

    refreshConversations().then((list) => {
      if (cancelled || !list || list.length === 0) return;
      openConversation(list[0].id);
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  // ---- opening / switching / creating conversations ----

  async function openConversation(conversationId: string) {
    if (!accessToken) return;
    setError(null);
    setActiveConversationId(conversationId);
    setMessages([]);
    setOldestLoadedCreatedAt(null);
    setHasMoreOlder(false);
    try {
      const page = await apiRequest<ConversationMessagePublic[]>(
        `/ai/orchestrator/conversations/${conversationId}/messages?limit=${MESSAGES_PAGE_SIZE}`,
        { token: accessToken },
      );
      shouldScrollToBottomRef.current = true;
      setMessages(page.map(toChatMessage));
      setOldestLoadedCreatedAt(page[0]?.created_at ?? null);
      setHasMoreOlder(page.length === MESSAGES_PAGE_SIZE);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this conversation");
    }
  }

  async function startNewConversation() {
    if (!accessToken) return;
    setError(null);
    try {
      const conversation = await apiRequest<ConversationPublic>("/ai/orchestrator/conversations", {
        method: "POST",
        token: accessToken,
      });
      setConversations((current) => [{ ...conversation, last_message_preview: null }, ...current]);
      setActiveConversationId(conversation.id);
      setMessages([]);
      setOldestLoadedCreatedAt(null);
      setHasMoreOlder(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start a new conversation");
    }
  }

  async function loadOlderMessages() {
    if (!accessToken || !activeConversationId || !oldestLoadedCreatedAt || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const page = await apiRequest<ConversationMessagePublic[]>(
        `/ai/orchestrator/conversations/${activeConversationId}/messages` +
          `?limit=${MESSAGES_PAGE_SIZE}&before=${encodeURIComponent(oldestLoadedCreatedAt)}`,
        { token: accessToken },
      );
      shouldScrollToBottomRef.current = false; // stay in place, don't jump to bottom
      setMessages((current) => [...page.map(toChatMessage), ...current]);
      if (page.length > 0) setOldestLoadedCreatedAt(page[0].created_at);
      setHasMoreOlder(page.length === MESSAGES_PAGE_SIZE);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load older messages");
    } finally {
      setLoadingOlder(false);
    }
  }

  // ---- sending a message ----

  async function send() {
    const text = draft.trim();
    if (!text || !accessToken || sending) return;

    shouldScrollToBottomRef.current = true;
    setMessages((current) => [...current, { role: "user", text }]);
    setDraft("");
    setSending(true);
    setError(null);
    try {
      const response = await apiRequest<OrchestratorChatResponse>("/ai/orchestrator/chat", {
        method: "POST",
        body: { message: text, conversation_id: activeConversationId },
        token: accessToken,
      });
      shouldScrollToBottomRef.current = true;
      setMessages((current) => [...current, { role: "assistant", text: response.reply, intent: response.intent }]);

      const isNewConversation = response.conversation_id !== activeConversationId;
      setActiveConversationId(response.conversation_id);
      setConversations((current) => {
        const preview = response.reply.slice(0, 140);
        const now = new Date().toISOString();
        if (isNewConversation) {
          return [{ id: response.conversation_id, title: null, created_at: now, updated_at: now, last_message_preview: preview }, ...current];
        }
        const rest = current.filter((c) => c.id !== response.conversation_id);
        const existing = current.find((c) => c.id === response.conversation_id);
        return [{ ...(existing ?? { id: response.conversation_id, title: null, created_at: now }), updated_at: now, last_message_preview: preview }, ...rest];
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the assistant");
    } finally {
      setSending(false);
    }
  }

  // Auto-scroll to bottom only for genuinely new messages (initial open,
  // send/receive) — never when older messages were just prepended above.
  useEffect(() => {
    if (shouldScrollToBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ block: "end" });
      shouldScrollToBottomRef.current = false;
    }
  }, [messages]);

  return (
    <section style={{ display: "flex", gap: "1rem", height: "70vh" }}>
      <aside className="tile" style={{ width: "260px", flexShrink: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="tile__header">
          <span className="eyebrow">Conversations</span>
        </div>
        <button onClick={startNewConversation} style={{ margin: "0.5rem 0" }}>
          + New conversation
        </button>
        <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          {conversations.length === 0 && <p className="eyebrow">No conversations yet.</p>}
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              onClick={() => openConversation(conversation.id)}
              style={{
                textAlign: "left",
                background: conversation.id === activeConversationId ? "var(--tile-active-bg, #2a2a3a)" : "transparent",
                border: "none",
                borderRadius: "0.4rem",
                padding: "0.5rem",
                cursor: "pointer",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{conversation.title ?? "Conversation"}</div>
              {conversation.last_message_preview && (
                <div className="eyebrow" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {conversation.last_message_preview}
                </div>
              )}
            </button>
          ))}
        </div>
      </aside>

      <div className="tile" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div className="tile__header">
          <span className="eyebrow">Banking assistant</span>
        </div>
        {error && <p role="alert">{error}</p>}

        {/* Fixed-height, internally scrollable message list — never grows the page. */}
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.6rem", marginTop: "0.75rem" }}>
          {hasMoreOlder && (
            <button onClick={loadOlderMessages} disabled={loadingOlder} style={{ alignSelf: "center" }}>
              {loadingOlder ? "Loading…" : "Load older messages"}
            </button>
          )}
          {messages.length === 0 && <p>Ask about your spending, budgets, savings, cashback, or credit.</p>}
          {messages.map((message, index) => (
            <div
              key={index}
              className="tile"
              style={{
                alignSelf: message.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "80%",
                whiteSpace: "pre-wrap",
              }}
            >
              {message.intent && (
                <span className="tag tag--neutral" style={{ marginBottom: "0.4rem", display: "inline-block" }}>
                  {INTENT_LABEL[message.intent]}
                </span>
              )}
              {message.text}
            </div>
          ))}
          {sending && <p className="eyebrow">Thinking…</p>}
          <div ref={messagesEndRef} />
        </div>

        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask the assistant…"
            style={{ flex: 1 }}
            disabled={sending}
          />
          <button onClick={send} disabled={sending || !draft.trim()}>
            Send
          </button>
        </div>
      </div>
    </section>
  );
}

import { Bot, CreditCard, LifeBuoy, Plus, Sparkles, Trash2, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { ASSISTANT_NAME, ASSISTANT_QUICK_ACTIONS } from "../config/assistant";
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

const QUICK_ACTION_ICON: Record<OrchestratorIntent, LucideIcon> = {
  personal_finance: Wallet,
  credit: CreditCard,
  support: LifeBuoy,
  greeting: Bot,
  out_of_scope: Bot,
};

const MESSAGES_PAGE_SIZE = 50;

function toChatMessage(entry: ConversationMessagePublic): ChatMessage {
  return {
    role: entry.role === "assistant" ? "assistant" : "user",
    text: entry.content,
    intent: entry.agent_used ?? undefined,
  };
}

function conversationTitle(conversation: ConversationSummary): string {
  return conversation.title ?? "New conversation";
}

export function AssistantPage() {
  const { user, accessToken } = useAuth();
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
  const draftInputRef = useRef<HTMLInputElement | null>(null);

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

  // ---- opening / switching / creating / deleting conversations ----

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

  async function deleteConversation(conversationId: string) {
    if (!accessToken) return;
    setError(null);
    try {
      await apiRequest<void>(`/ai/orchestrator/conversations/${conversationId}`, {
        method: "DELETE",
        token: accessToken,
      });
      setConversations((current) => current.filter((c) => c.id !== conversationId));
      if (activeConversationId === conversationId) {
        setActiveConversationId(null);
        setMessages([]);
        setOldestLoadedCreatedAt(null);
        setHasMoreOlder(false);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete this conversation");
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

  // ---- quick actions ----

  function applyStarterPrompt(prompt: string) {
    setDraft(prompt);
    draftInputRef.current?.focus();
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
      setActiveConversationId(response.conversation_id);
      // Re-fetch rather than optimistically patch state: the backend may
      // have just generated a real title for this conversation (see
      // OrchestratorService._maybe_generate_title) and this is the
      // simplest way to pick it up without duplicating that logic here.
      await refreshConversations();
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
    <section className="assistant-layout">
      <aside className="tile assistant-sidebar">
        <div className="tile__header">
          <span className="eyebrow">Conversations</span>
        </div>
        <button className="assistant-sidebar__new" onClick={startNewConversation} type="button">
          <Plus size={14} /> New conversation
        </button>
        <div className="assistant-conversation-list">
          {conversations.length === 0 && <p className="empty-state">No conversations yet.</p>}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`assistant-conversation ${
                conversation.id === activeConversationId ? "assistant-conversation--active" : ""
              }`}
            >
              <button className="assistant-conversation__open" onClick={() => openConversation(conversation.id)} type="button">
                <span className="assistant-conversation__title">{conversationTitle(conversation)}</span>
              </button>
              <button
                className="assistant-conversation__delete"
                aria-label="Delete conversation"
                onClick={() => deleteConversation(conversation.id)}
                type="button"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      <div className="assistant-main">
        <div className="tile assistant-hero">
          <div className="assistant-hero__top">
            <div className="assistant-hero__avatar">
              <Sparkles size={20} />
            </div>
            <div>
              <p className="assistant-hero__title">
                <strong>
                  Hi {user?.first_name}! I'm {ASSISTANT_NAME}, your AI assistant.
                </strong>
              </p>
              <p className="assistant-hero__subtitle">
                I orchestrate a team of specialised agents to help you with spending, budgets, savings, cashback, and
                credit.
              </p>
            </div>
          </div>
          <div className="assistant-quick-actions">
            {ASSISTANT_QUICK_ACTIONS.map((action, index) => {
              const Icon = QUICK_ACTION_ICON[action.intent];
              return (
                <button
                  key={action.intent}
                  className={`assistant-quick-action ${index === 0 ? "assistant-quick-action--primary" : ""}`}
                  onClick={() => applyStarterPrompt(action.starterPrompt)}
                  type="button"
                >
                  <Icon size={15} /> {action.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="tile assistant-chat">
          {error && <p role="alert">{error}</p>}

          {/* Fixed-height, internally scrollable message list — never grows the page. */}
          <div className="assistant-messages">
            {hasMoreOlder && (
              <button onClick={loadOlderMessages} disabled={loadingOlder} style={{ alignSelf: "center" }} type="button">
                {loadingOlder ? "Loading…" : "Load older messages"}
              </button>
            )}
            {messages.length === 0 && (
              <p className="empty-state">Ask about your spending, budgets, savings, cashback, or credit.</p>
            )}
            {messages.map((message, index) => (
              <div key={index} className={`assistant-message assistant-message--${message.role}`}>
                <div className={`assistant-bubble assistant-bubble--${message.role}`}>{message.text}</div>
                {message.role === "assistant" && message.intent && (
                  <span className="assistant-message__agent">
                    <Bot size={11} /> {INTENT_LABEL[message.intent]}
                  </span>
                )}
              </div>
            ))}
            {sending && <p className="eyebrow">Thinking…</p>}
            <div ref={messagesEndRef} />
          </div>

          <div className="assistant-composer">
            <input
              ref={draftInputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask the assistant…"
              disabled={sending}
            />
            <button onClick={send} disabled={sending || !draft.trim()} type="button">
              Send
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

import { Bot, Check, Copy, CreditCard, Download, LifeBuoy, MessageCircle, Plus, Send, Sparkles, Trash2, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import { ASSISTANT_NAME, ASSISTANT_QUICK_ACTIONS } from "../config/assistant";
import { FinancialActionConfirmCard } from "../features/assistant";
import { useAuth } from "../hooks/useAuth";
import type {
  ActionCard,
  AgentActionStatus,
  ConversationMessagePublic,
  ConversationPublic,
  ConversationSummary,
  DownloadAttachment,
  OrchestratorChatResponse,
  OrchestratorIntent,
} from "../types";
import { downloadBlob } from "../utils";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  intent?: OrchestratorIntent;
  createdAt: string;
  /** Only ever set on the assistant reply just received this session — the
   * backend doesn't persist suggested followups. */
  followups?: string[];
  /** Persisted (ai_conversation_messages.action_id): the drafted action's
   * id. On reopen we fetch its current state into actionCard/actionStatus. */
  actionId?: string;
  actionCard?: ActionCard;
  actionStatus?: AgentActionStatus;
  actionDetail?: string | null;
  /** Only ever set on the assistant reply just received this session, same
   * as followups — the underlying export endpoint works anytime, so
   * there's nothing to persist or reconstruct on reopen. */
  download?: DownloadAttachment;
}

const QUICK_ACTION_ICON: Record<OrchestratorIntent, LucideIcon> = {
  personal_finance: Wallet,
  credit: CreditCard,
  support: LifeBuoy,
  action: Send,
  greeting: Bot,
  out_of_scope: Bot,
};

const MESSAGES_PAGE_SIZE = 50;

function toChatMessage(entry: ConversationMessagePublic): ChatMessage {
  return {
    role: entry.role === "assistant" ? "assistant" : "user",
    text: entry.content,
    intent: entry.agent_used ?? undefined,
    createdAt: entry.created_at,
    actionId: entry.action_id ?? undefined,
    actionCard: entry.action?.card ?? undefined,
    actionStatus: entry.action?.status,
    actionDetail: entry.action?.error_detail,
  };
}

function formatMessageTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

export function AssistantPage() {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const conversationTitle = (conversation: ConversationSummary): string =>
    conversation.title ?? t("assistant.newConversationTitle");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [oldestLoadedCreatedAt, setOldestLoadedCreatedAt] = useState<string | null>(null);
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [conversationSearch, setConversationSearch] = useState("");

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
      setError(err instanceof ApiError ? err.message : t("assistant.couldNotLoadConversations"));
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
      setError(err instanceof ApiError ? err.message : t("assistant.couldNotLoadConversation"));
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
      setError(err instanceof ApiError ? err.message : t("assistant.couldNotStartConversation"));
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
      setError(err instanceof ApiError ? err.message : t("assistant.couldNotDeleteConversation"));
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
      setError(err instanceof ApiError ? err.message : t("assistant.couldNotLoadOlderMessages"));
    } finally {
      setLoadingOlder(false);
    }
  }

  // ---- quick actions ----

  function applyStarterPrompt(prompt: string) {
    setDraft(prompt);
    draftInputRef.current?.focus();
  }

  // ---- copy-to-clipboard ----

  async function copyMessage(index: number, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex((current) => (current === index ? null : current)), 1500);
    } catch {
      // Clipboard permission denied/unavailable — nothing worth surfacing an error for.
    }
  }

  // ---- sending a message ----

  async function sendMessage(text: string) {
    if (!text || !accessToken || sending) return;

    shouldScrollToBottomRef.current = true;
    setMessages((current) => [...current, { role: "user", text, createdAt: new Date().toISOString() }]);
    setSending(true);
    setError(null);
    try {
      const response = await apiRequest<OrchestratorChatResponse>("/ai/orchestrator/chat", {
        method: "POST",
        body: { message: text, conversation_id: activeConversationId },
        token: accessToken,
      });
      shouldScrollToBottomRef.current = true;
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.reply,
          intent: response.intent,
          createdAt: new Date().toISOString(),
          followups: response.suggested_followups,
          actionId: response.action_card?.action_id,
          actionCard: response.action_card ?? undefined,
          actionStatus: response.action_card ? "DRAFT" : undefined,
          download: response.download ?? undefined,
        },
      ]);
      setActiveConversationId(response.conversation_id);
      // Re-fetch rather than optimistically patch state: the backend may
      // have just generated a real title for this conversation (see
      // OrchestratorService._maybe_generate_title) and this is the
      // simplest way to pick it up without duplicating that logic here.
      await refreshConversations();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("assistant.couldNotReachAssistant"));
    } finally {
      setSending(false);
    }
  }

  function send() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    void sendMessage(text);
  }

  function sendFollowup(text: string) {
    void sendMessage(text);
  }

  async function downloadAttachment(attachment: DownloadAttachment) {
    if (!accessToken) return;
    const response = await fetch(`${API_BASE_URL}${attachment.url}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      setError(t("assistant.couldNotDownload"));
      return;
    }
    await downloadBlob(response, "statement.pdf");
  }

  // Auto-scroll to bottom only for genuinely new messages (initial open,
  // send/receive) — never when older messages were just prepended above.
  useEffect(() => {
    if (shouldScrollToBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ block: "end" });
      shouldScrollToBottomRef.current = false;
    }
  }, [messages]);

  const filteredConversations = conversations.filter((conversation) =>
    conversationTitle(conversation).toLowerCase().includes(conversationSearch.trim().toLowerCase()),
  );

  return (
    <section className="assistant-layout">
      <aside className="tile assistant-sidebar">
        <div className="tile__header">
          <span className="eyebrow">{t("assistant.conversations")}</span>
        </div>
        <button className="assistant-sidebar__new" onClick={startNewConversation} type="button">
          <Plus size={16} /> {t("assistant.newConversation")}
        </button>
        <input
          className="assistant-sidebar__search"
          value={conversationSearch}
          onChange={(e) => setConversationSearch(e.target.value)}
          placeholder={t("assistant.searchConversations")}
          type="search"
        />
        <div className="assistant-conversation-list">
          {conversations.length === 0 && <p className="empty-state">{t("assistant.noConversationsYet")}</p>}
          {conversations.length > 0 && filteredConversations.length === 0 && (
            <p className="empty-state">{t("assistant.noConversationsMatch")}</p>
          )}
          {filteredConversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`assistant-conversation ${
                conversation.id === activeConversationId ? "assistant-conversation--active" : ""
              }`}
            >
              <button className="assistant-conversation__open" onClick={() => openConversation(conversation.id)} type="button">
                <span className="assistant-conversation__icon">
                  <MessageCircle size={13} />
                </span>
                <span className="assistant-conversation__title">{conversationTitle(conversation)}</span>
              </button>
              <button
                className="assistant-conversation__delete"
                aria-label={t("assistant.deleteConversation")}
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
                <strong>{t("assistant.greeting", { name: user?.first_name, assistantName: ASSISTANT_NAME })}</strong>
              </p>
              <p className="assistant-hero__subtitle">{t("assistant.heroSubtitle")}</p>
            </div>
          </div>
          <div className="assistant-quick-actions">
            {ASSISTANT_QUICK_ACTIONS.map((action) => {
              const Icon = QUICK_ACTION_ICON[action.intent];
              return (
                <button
                  key={action.intent}
                  className="assistant-quick-action"
                  onClick={() => applyStarterPrompt(action.starterPrompt)}
                  type="button"
                >
                  <Icon size={15} /> {t(action.labelKey)}
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
                {loadingOlder ? t("assistant.loading") : t("assistant.loadOlderMessages")}
              </button>
            )}
            {messages.length === 0 && (
              <p className="empty-state">{t("assistant.askAbout")}</p>
            )}
            {messages.map((message, index) => (
              <div key={index} className={`assistant-message assistant-message--${message.role}`}>
                <div className={`assistant-bubble assistant-bubble--${message.role}`}>{message.text}</div>
                {message.role === "assistant" && message.intent && (
                  <span className="assistant-message__agent">
                    <Bot size={11} /> {t(`assistant.intent.${message.intent}`)}
                  </span>
                )}
                {message.role === "assistant" && message.actionCard && (
                  <FinancialActionConfirmCard
                    key={message.actionStatus ?? "DRAFT"}
                    card={message.actionCard}
                    token={accessToken}
                    initialStatus={message.actionStatus}
                    initialDetail={message.actionDetail}
                  />
                )}
                {message.role === "assistant" && message.download && (
                  <button
                    type="button"
                    className="assistant-download"
                    onClick={() => void downloadAttachment(message.download!)}
                  >
                    <Download size={13} /> {t("assistant.downloadStatement")}
                  </button>
                )}
                <div className="assistant-message__meta">
                  <span className="assistant-message__time">{formatMessageTime(message.createdAt)}</span>
                  <button
                    className="assistant-message__copy"
                    aria-label={t("assistant.copyMessage")}
                    onClick={() => copyMessage(index, message.text)}
                    type="button"
                  >
                    {copiedIndex === index ? <Check size={12} /> : <Copy size={12} />}
                  </button>
                </div>
                {message.role === "assistant" && message.followups && message.followups.length > 0 && (
                  <div className="assistant-followups">
                    {message.followups.map((followup) => (
                      <button
                        key={followup}
                        className="assistant-followup"
                        onClick={() => sendFollowup(followup)}
                        disabled={sending}
                        type="button"
                      >
                        {followup}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {sending && <p className="eyebrow">{t("assistant.thinking")}</p>}
            <div ref={messagesEndRef} />
          </div>

          <div className="assistant-composer">
            <input
              ref={draftInputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder={t("assistant.askThePlaceholder")}
              disabled={sending}
            />
            <button onClick={send} disabled={sending || !draft.trim()} type="button">
              {t("assistant.send")}
            </button>
          </div>
          <p className="assistant-disclaimer">{t("assistant.disclaimer", { assistantName: ASSISTANT_NAME })}</p>
        </div>
      </div>
    </section>
  );
}

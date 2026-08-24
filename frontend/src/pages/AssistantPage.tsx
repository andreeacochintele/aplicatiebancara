import { useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { OrchestratorChatResponse, OrchestratorIntent } from "../types";

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

export function AssistantPage() {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const text = draft.trim();
    if (!text || !accessToken || sending) return;

    setMessages((current) => [...current, { role: "user", text }]);
    setDraft("");
    setSending(true);
    setError(null);
    try {
      const response = await apiRequest<OrchestratorChatResponse>("/ai/orchestrator/chat", {
        method: "POST",
        body: { message: text },
        token: accessToken,
      });
      setMessages((current) => [...current, { role: "assistant", text: response.reply, intent: response.intent }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the assistant");
    } finally {
      setSending(false);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Banking assistant</span>
        </div>
        {error && <p role="alert">{error}</p>}

        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginTop: "0.75rem" }}>
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

import { ArrowRight, Check, Clock, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError, apiRequest } from "../../api/apiClient";
import type { AgentActionResult, AgentActionStatus, PhoneTransferConfirmCard as CardModel } from "../../types";

const TERMINAL_COPY: Partial<Record<AgentActionStatus, { label: string; tone: "ok" | "bad" }>> = {
  EXECUTED: { label: "Transfer trimis", tone: "ok" },
  CANCELLED: { label: "Anulat", tone: "bad" },
  EXPIRED: { label: "Draftul a expirat", tone: "bad" },
  FAILED: { label: "Transferul a eșuat", tone: "bad" },
  NEEDS_REVIEW: { label: "Verificare de siguranță necesară", tone: "bad" },
  SUPERSEDED: { label: "Înlocuit de o cerere mai nouă", tone: "bad" },
};

function useSecondsLeft(expiresAt: string): number {
  const target = useMemo(() => new Date(expiresAt).getTime(), [expiresAt]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return Math.max(0, Math.round((target - now) / 1000));
}

export function PhoneTransferConfirmCard({ card, token }: { card: CardModel; token: string | null }) {
  const [result, setResult] = useState<AgentActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const secondsLeft = useSecondsLeft(card.expires_at);

  const status: AgentActionStatus = result?.status ?? "DRAFT";
  const isDraft = status === "DRAFT";
  const expired = isDraft && secondsLeft <= 0;
  const terminal = !isDraft ? TERMINAL_COPY[status] : undefined;

  async function act(kind: "confirm" | "cancel") {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiRequest<AgentActionResult>(`/ai/actions/${card.action_id}/${kind}`, {
        method: "POST",
        token,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Nu am putut procesa acțiunea.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="assistant-action-card">
      <div className="assistant-action-card__title">Confirmă transferul</div>

      <div className="assistant-action-card__row">
        <span className="assistant-action-card__label">Către</span>
        <span className="assistant-action-card__value">
          {card.recipient_name}
          {card.recipient_phone_masked ? ` · ${card.recipient_phone_masked}` : ""}
        </span>
      </div>
      <div className="assistant-action-card__row">
        <span className="assistant-action-card__label">Sumă</span>
        <span className="assistant-action-card__value assistant-action-card__amount">
          {card.amount} {card.currency}
        </span>
      </div>
      <div className="assistant-action-card__row">
        <span className="assistant-action-card__label">Din</span>
        <span className="assistant-action-card__value">{card.source_wallet_label}</span>
      </div>

      {error && (
        <p className="assistant-action-card__status assistant-action-card__status--bad" role="alert">
          {error}
        </p>
      )}

      {terminal && (
        <p
          className={`assistant-action-card__status assistant-action-card__status--${terminal.tone}`}
          role="status"
        >
          {terminal.tone === "ok" ? <Check size={14} /> : <X size={14} />}
          {terminal.label}
          {result?.error_detail ? ` — ${result.error_detail}` : ""}
        </p>
      )}

      {isDraft && !expired && (
        <>
          <div className="assistant-action-card__actions">
            <button type="button" onClick={() => act("confirm")} disabled={busy}>
              <ArrowRight size={15} /> Accept
            </button>
            <button type="button" className="button--ghost" onClick={() => act("cancel")} disabled={busy}>
              Anulează
            </button>
          </div>
          <p className="assistant-action-card__timer">
            <Clock size={12} /> expiră în {Math.floor(secondsLeft / 60)}:
            {String(secondsLeft % 60).padStart(2, "0")}
          </p>
        </>
      )}

      {expired && (
        <p className="assistant-action-card__status assistant-action-card__status--bad" role="status">
          <X size={14} /> Draftul a expirat. Cere transferul din nou.
        </p>
      )}
    </div>
  );
}

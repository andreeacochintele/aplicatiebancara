import { ArrowRight, Check, Clock, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../../api/apiClient";
import type { AgentActionResult, AgentActionStatus, PhoneTransferConfirmCard as CardModel } from "../../types";

const TERMINAL_TONE: Partial<Record<AgentActionStatus, "ok" | "bad">> = {
  EXECUTED: "ok",
  CANCELLED: "bad",
  EXPIRED: "bad",
  FAILED: "bad",
  NEEDS_REVIEW: "bad",
  SUPERSEDED: "bad",
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

export function PhoneTransferConfirmCard({
  card,
  token,
  initialStatus,
  initialDetail,
}: {
  card: CardModel;
  token: string | null;
  /** Set when re-hydrating a reopened conversation — the action's current
   * server-side status, so a confirmed/cancelled card comes back terminal
   * instead of showing live buttons again. */
  initialStatus?: AgentActionStatus;
  initialDetail?: string | null;
}) {
  const [result, setResult] = useState<AgentActionResult | null>(() =>
    initialStatus && initialStatus !== "DRAFT"
      ? {
          action_id: card.action_id,
          type: "phone_transfer",
          status: initialStatus,
          result_transaction_id: null,
          error_code: null,
          error_detail: initialDetail ?? null,
          card,
        }
      : null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const secondsLeft = useSecondsLeft(card.expires_at);
  const { t } = useTranslation();

  const status: AgentActionStatus = result?.status ?? "DRAFT";
  const isDraft = status === "DRAFT";
  const expired = isDraft && secondsLeft <= 0;
  const terminalTone = !isDraft ? TERMINAL_TONE[status] : undefined;

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
      setError(err instanceof ApiError ? err.message : t("assistant.actionCard.couldNotProcess"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="assistant-action-card">
      <div className="assistant-action-card__title">
        {terminalTone || expired ? t("assistant.actionCard.titleTransfer") : t("assistant.actionCard.titleConfirm")}
      </div>

      <div className="assistant-action-card__row">
        <span className="assistant-action-card__label">{t("assistant.actionCard.to")}</span>
        <span className="assistant-action-card__value">
          {card.recipient_name}
          {card.recipient_phone_masked ? ` · ${card.recipient_phone_masked}` : ""}
        </span>
      </div>
      <div className="assistant-action-card__row">
        <span className="assistant-action-card__label">{t("assistant.actionCard.amount")}</span>
        <span className="assistant-action-card__value assistant-action-card__amount">
          {card.amount} {card.currency}
        </span>
      </div>
      <div className="assistant-action-card__row">
        <span className="assistant-action-card__label">{t("assistant.actionCard.from")}</span>
        <span className="assistant-action-card__value">{card.source_wallet_label}</span>
      </div>

      {error && (
        <p className="assistant-action-card__status assistant-action-card__status--bad" role="alert">
          {error}
        </p>
      )}

      {terminalTone && (
        <p
          className={`assistant-action-card__status assistant-action-card__status--${terminalTone}`}
          role="status"
        >
          {terminalTone === "ok" ? <Check size={14} /> : <X size={14} />}
          {t(`assistant.actionCard.status.${status}`)}
          {result?.error_detail ? ` — ${result.error_detail}` : ""}
        </p>
      )}

      {isDraft && !expired && (
        <>
          <div className="assistant-action-card__actions">
            <button type="button" onClick={() => act("confirm")} disabled={busy}>
              <ArrowRight size={15} /> {t("assistant.actionCard.accept")}
            </button>
            <button type="button" className="button--ghost" onClick={() => act("cancel")} disabled={busy}>
              {t("assistant.actionCard.cancel")}
            </button>
          </div>
          <p className="assistant-action-card__timer">
            <Clock size={12} /> {t("assistant.actionCard.expiresIn")} {Math.floor(secondsLeft / 60)}:
            {String(secondsLeft % 60).padStart(2, "0")}
          </p>
        </>
      )}

      {expired && (
        <p className="assistant-action-card__status assistant-action-card__status--bad" role="status">
          <X size={14} /> {t("assistant.actionCard.draftExpired")}
        </p>
      )}
    </div>
  );
}

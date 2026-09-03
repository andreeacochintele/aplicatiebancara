import { ArrowRight, Check, Clock, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../../api/apiClient";
import type { ActionCard, AgentActionResult, AgentActionStatus } from "../../types";

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

function cardTitle(card: ActionCard, t: (key: string) => string): string {
  if (card.kind === "loan_payment_confirm") return card.title;
  if (card.kind === "credit_card_repayment_confirm") return card.card_label;
  if (card.kind === "credit_card_generation_confirm") return card.card_label;
  if (card.kind === "wallet_generation_confirm") return t("assistant.actionCard.currentAccounts");
  return card.recipient_name;
}

function cardRows(card: ActionCard, t: (key: string) => string): Array<[string, string]> {
  if (card.kind === "loan_payment_confirm") {
    return [
      [t("assistant.actionCard.amount"), `${card.amount} ${card.currency}`],
      [t("assistant.actionCard.from"), card.source_wallet_label],
      [t("assistant.actionCard.outstanding"), `${card.outstanding_principal} ${card.currency}`],
      ...(card.next_payment_date ? [[t("assistant.actionCard.dueDate"), new Date(card.next_payment_date).toLocaleDateString()]] as Array<[string, string]> : []),
    ];
  }
  if (card.kind === "credit_card_repayment_confirm") {
    return [
      [t("assistant.actionCard.amount"), `${card.amount} ${card.currency}`],
      [t("assistant.actionCard.from"), card.source_wallet_label],
      [t("assistant.actionCard.balanceDue"), `${card.balance_due} ${card.currency}`],
    ];
  }
  if (card.kind === "credit_card_generation_confirm") {
    return [
      [t("assistant.actionCard.tier"), card.tier],
      [t("assistant.actionCard.creditLimit"), `${card.credit_limit} ${card.currency}`],
      [t("assistant.actionCard.collateral"), card.collateral_wallet_label ?? t("assistant.actionCard.chooseCollateral")],
    ];
  }
  if (card.kind === "wallet_generation_confirm") {
    return [[t("assistant.actionCard.currency"), card.currency ?? t("assistant.actionCard.chooseCurrency")]];
  }
  return [
    [t("assistant.actionCard.to"), `${card.recipient_name}${card.recipient_phone_masked ? ` · ${card.recipient_phone_masked}` : ""}`],
    [t("assistant.actionCard.amount"), `${card.amount} ${card.currency}`],
    [t("assistant.actionCard.from"), card.source_wallet_label],
  ];
}

export function FinancialActionConfirmCard({
  card,
  token,
  initialStatus,
  initialDetail,
}: {
  card: ActionCard;
  token: string | null;
  initialStatus?: AgentActionStatus;
  initialDetail?: string | null;
}) {
  const [result, setResult] = useState<AgentActionResult | null>(() =>
    initialStatus && initialStatus !== "DRAFT"
      ? {
          action_id: card.action_id,
          type: card.kind,
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
  const currentCard = result?.card ?? card;

  const status: AgentActionStatus = result?.status ?? "DRAFT";
  const isDraft = status === "DRAFT";
  const expired = isDraft && secondsLeft <= 0;
  const terminalTone = !isDraft ? TERMINAL_TONE[status] : undefined;
  const titleKey =
    currentCard.kind === "phone_transfer_confirm"
      ? "titleTransfer"
      : currentCard.kind === "credit_card_generation_confirm"
        ? "titleCard"
        : currentCard.kind === "wallet_generation_confirm"
          ? "titleWallet"
        : "titlePayment";
  const needsCollateral =
    currentCard.kind === "credit_card_generation_confirm" && currentCard.collateral_wallet_id === null;
  const needsCurrency = currentCard.kind === "wallet_generation_confirm" && currentCard.currency === null;

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

  async function selectCollateral(walletId: string) {
    if (!token || busy || currentCard.kind !== "credit_card_generation_confirm") return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiRequest<AgentActionResult>(`/ai/actions/${currentCard.action_id}/credit-card-collateral`, {
        method: "POST",
        token,
        body: { wallet_id: walletId },
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("assistant.actionCard.couldNotProcess"));
    } finally {
      setBusy(false);
    }
  }

  async function selectWalletCurrency(currency: string) {
    if (!token || busy || currentCard.kind !== "wallet_generation_confirm") return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiRequest<AgentActionResult>(`/ai/actions/${currentCard.action_id}/wallet-currency`, {
        method: "POST",
        token,
        body: { currency },
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
        {terminalTone || expired ? t(`assistant.actionCard.${titleKey}`) : t("assistant.actionCard.titleConfirm")}
      </div>

      <div className="assistant-action-card__row">
        <span className="assistant-action-card__label">{t("assistant.actionCard.action")}</span>
        <span className="assistant-action-card__value">{cardTitle(currentCard, t)}</span>
      </div>
      {cardRows(currentCard, t).map(([label, value]) => (
        <div className="assistant-action-card__row" key={label}>
          <span className="assistant-action-card__label">{label}</span>
          <span className="assistant-action-card__value">{value}</span>
        </div>
      ))}

      {isDraft && !expired && currentCard.kind === "credit_card_generation_confirm" && currentCard.collateral_options.length > 0 && (
        <div className="assistant-collateral-options">
          {currentCard.collateral_options.map((option) => {
            const selected = option.wallet_id === currentCard.collateral_wallet_id;
            return (
              <button
                key={`${option.kind}-${option.wallet_id}-${option.label}`}
                className={selected ? "assistant-collateral-option assistant-collateral-option--selected" : "assistant-collateral-option"}
                type="button"
                onClick={() => selectCollateral(option.wallet_id)}
                disabled={busy || selected}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      )}

      {isDraft && !expired && currentCard.kind === "wallet_generation_confirm" && currentCard.currency_options.length > 0 && (
        <div className="assistant-currency-options">
          {currentCard.currency_options.map((option) => {
            const selected = option.currency === currentCard.currency;
            return (
              <button
                key={option.currency}
                className={selected ? "assistant-currency-option assistant-currency-option--selected" : "assistant-currency-option"}
                type="button"
                onClick={() => selectWalletCurrency(option.currency)}
                disabled={busy || selected}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      )}

      {error && (
        <p className="assistant-action-card__status assistant-action-card__status--bad" role="alert">
          {error}
        </p>
      )}

      {terminalTone && (
        <p className={`assistant-action-card__status assistant-action-card__status--${terminalTone}`} role="status">
          {terminalTone === "ok" ? <Check size={14} /> : <X size={14} />}
          {t(`assistant.actionCard.status.${status}`)}
          {result?.error_detail ? ` - ${result.error_detail}` : ""}
        </p>
      )}

      {isDraft && !expired && (
        <>
          <div className="assistant-action-card__actions">
            <button type="button" onClick={() => act("confirm")} disabled={busy || needsCollateral || needsCurrency}>
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

import {
  ArrowDownRight, ArrowUpRight, ChevronRight, Eye, EyeOff,
  Receipt, RefreshCcw, Send, Sparkles, TrendingDown, TrendingUp, Users, type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { apiRequest } from "../api/apiClient";
import { PeriodSelect } from "../components/PeriodSelect";
import { useAuth } from "../hooks/useAuth";
import { usePeriod } from "../hooks/usePeriod";
import type { CreditScore, NetWorthResponse, ScheduledPayment, SpendingByTypeResponse, Transaction } from "../types";

const QUICK_ACTIONS: { to: string; labelKey: string; subKey: string; icon: LucideIcon }[] = [
  { to: "/payments", labelKey: "dashboard.send", subKey: "dashboard.newTransfer", icon: Send },
  { to: "/wallets", labelKey: "dashboard.convert", subKey: "dashboard.exchangeFx", icon: RefreshCcw },
  { to: "/transactions", labelKey: "dashboard.review", subKey: "dashboard.allTransactions", icon: Receipt },
  { to: "/assistant", labelKey: "dashboard.ask", subKey: "dashboard.assistant", icon: Sparkles },
];

const BUSINESS_QUICK_ACTIONS: { to: string; labelKey: string; subKey: string; icon: LucideIcon }[] = [
  { to: "/payments", labelKey: "dashboard.send", subKey: "dashboard.newTransfer", icon: Send },
  { to: "/business/bulk-transfer", labelKey: "dashboard.bulkTransfer", subKey: "dashboard.payManyAtOnce", icon: Users },
  { to: "/transactions", labelKey: "dashboard.review", subKey: "dashboard.allTransactions", icon: Receipt },
  { to: "/assistant", labelKey: "dashboard.ask", subKey: "dashboard.assistant", icon: Sparkles },
];

const STATUS_CHIP: Record<string, string> = {
  COMPLETED: "easyb-chip-green",
  PENDING_REVIEW: "easyb-chip-violet",
  PROCESSING: "easyb-chip-violet",
  CREATED: "easyb-chip-neutral",
  FAILED: "easyb-chip-red",
  REJECTED: "easyb-chip-red",
  CANCELLED: "easyb-chip-red",
};

const CREDIT_BAND_LABEL_KEY: Record<string, string> = {
  EXCELLENT: "credit.excellent",
  VERY_GOOD: "credit.veryGood",
  GOOD: "credit.good",
  FAIR: "credit.fair",
  RISKY: "credit.risky",
};

function formatCreditBand(band: string, t: (key: string) => string): string {
  const key = CREDIT_BAND_LABEL_KEY[band];
  return key ? t(key) : band;
}

function hueFromString(value: string): number {
  return Math.abs([...value].reduce((sum, ch) => sum + ch.charCodeAt(0), 0)) % 360;
}

function colorForType(type: string): string {
  return `hsl(${hueFromString(type)} 62% 55%)`;
}

function formatAmount(transaction: Transaction, userWalletIds: Set<string>): { sign: string; text: string } {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  const sign = isIncoming && !isOutgoing ? "+" : "-";
  return { sign, text: `${transaction.amount} ${transaction.currency}` };
}

function formatTransactionType(
  transaction: Transaction,
  userWalletIds: Set<string>,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  const description = transaction.description?.toLowerCase() ?? "";
  if (description.includes("loan") && description.includes("disbursement") && isIncoming && !isOutgoing) {
    return t("dashboard.bankToUser");
  }
  if (transaction.type === "LOAN_PAYMENT") {
    return t("dashboard.userToBank");
  }
  return t(`common.txType.${transaction.type}`, { defaultValue: transaction.type.replaceAll("_", " ") });
}

export function DashboardPage() {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const { query: periodQuery } = usePeriod();
  const [hidden, setHidden] = useState(false);
  const [netWorth, setNetWorth] = useState<NetWorthResponse | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [spending, setSpending] = useState<SpendingByTypeResponse | null>(null);
  const [creditScore, setCreditScore] = useState<CreditScore | null>(null);
  const [scheduledPayments, setScheduledPayments] = useState<ScheduledPayment[]>([]);
  const [settingMainId, setSettingMainId] = useState<string | null>(null);
  const [showTotal, setShowTotal] = useState(false);
  const isBusiness = user?.user_type === "BUSINESS";

  function reloadNetWorth() {
    if (!accessToken) return;
    apiRequest<NetWorthResponse>("/analytics/net-worth", { token: accessToken })
      .then(setNetWorth)
      .catch(() => setNetWorth(null));
  }

  useEffect(() => {
    if (!accessToken) return;
    reloadNetWorth();
    apiRequest<Transaction[]>("/transactions", { token: accessToken })
      .then((list) => setTransactions([...list].sort((a, b) => b.created_at.localeCompare(a.created_at))))
      .catch(() => setTransactions([]));
    if (user?.user_type !== "BUSINESS") {
      // Credit is hidden for business accounts (personal FICO-style score,
      // personal loan products) — skip the fetch, not just the card below.
      apiRequest<CreditScore>("/credit/score", { token: accessToken })
        .then(setCreditScore)
        .catch(() => setCreditScore(null));
    } else {
      // Upcoming-payments widget replaces the credit-score card for business
      // accounts — skip this fetch for personal accounts, same reasoning.
      apiRequest<ScheduledPayment[]>("/payments/scheduled-payments", { token: accessToken })
        .then(setScheduledPayments)
        .catch(() => setScheduledPayments([]));
    }
  }, [accessToken, user?.user_type]);

  // Follows the app-wide month selector, so the dashboard's spending card and
  // the Analytics page never disagree about which month they are showing.
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    apiRequest<SpendingByTypeResponse>(`/analytics/spending-by-type?${periodQuery}`, { token: accessToken })
      .then((data) => !cancelled && setSpending(data))
      .catch(() => !cancelled && setSpending(null));
    return () => {
      cancelled = true;
    };
  }, [accessToken, periodQuery]);

  async function setMainWallet(walletId: string) {
    if (!accessToken || settingMainId) return;
    setSettingMainId(walletId);
    try {
      await apiRequest(`/wallets/${walletId}/set-main`, { method: "PATCH", token: accessToken });
      reloadNetWorth();
    } catch {
      // best-effort from this widget; the wallet chip simply stays as it was
    } finally {
      setSettingMainId(null);
    }
  }

  const userWalletIds = new Set(netWorth?.wallets.map((wallet) => wallet.wallet_id) ?? []);
  const recentTransactions = transactions.slice(0, 5);
  const needsAttention = transactions.filter((transaction) => transaction.status === "PENDING_REVIEW").slice(0, 3);

  // spending-by-type is grouped by (type, currency) server-side; only chart one
  // currency at a time so percentages aren't summed across mismatched units.
  const spendingCurrency = netWorth?.base_currency ?? spending?.items[0]?.currency;
  const spendingItems = spending?.items.filter((item) => item.currency === spendingCurrency) ?? [];
  const spendingTotal = spendingItems.reduce((sum, item) => sum + Number(item.total_amount), 0);
  const donutData = spendingItems.map((item) => ({
    key: `${item.type}-${item.currency}`,
    // Translated label, not the raw TransactionType enum value — this feeds
    // both the legend below and the Recharts Tooltip's `name`, which was
    // showing "CARD_PAYMENT" verbatim instead of "Card payment".
    name: t(`common.txType.${item.type}`, { defaultValue: item.type.toLowerCase().replaceAll("_", " ") }),
    value: Number(item.total_amount),
    color: colorForType(item.type),
  }));

  const scorePercent = creditScore ? Math.min(100, Math.max(0, ((creditScore.score - 300) / 550) * 100)) : 0;

  const quickActions = isBusiness ? BUSINESS_QUICK_ACTIONS : QUICK_ACTIONS;

  // Client-side month-to-date sum over already-fetched transactions — same
  // single-currency scoping as the spending donut above, so incoming and
  // outgoing are never blended across currencies.
  const now = new Date();
  const monthCashFlow = transactions.reduce(
    (totals, transaction) => {
      if (transaction.status !== "COMPLETED" || transaction.currency !== spendingCurrency) return totals;
      const created = new Date(transaction.created_at);
      if (created.getFullYear() !== now.getFullYear() || created.getMonth() !== now.getMonth()) return totals;
      const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
      const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
      if (isIncoming && !isOutgoing) totals.incoming += Number(transaction.amount);
      else if (isOutgoing && !isIncoming) totals.outgoing += Number(transaction.amount);
      return totals;
    },
    { incoming: 0, outgoing: 0 },
  );
  const netCashFlow = monthCashFlow.incoming - monthCashFlow.outgoing;

  const upcomingScheduledPayments = scheduledPayments
    .filter((payment) => payment.status === "ACTIVE")
    .sort((a, b) => a.next_run_on.localeCompare(b.next_run_on))
    .slice(0, 5);

  const mainWallet = netWorth?.wallets.find((wallet) => wallet.is_main);
  const heroAmount = showTotal ? netWorth?.total_available_balance : mainWallet?.available_balance;
  const heroLabel = !netWorth
    ? t("dashboard.welcome", { name: user?.first_name })
    : showTotal
      ? t("dashboard.totalBalanceAllWallets", { currency: netWorth.base_currency })
      : t("dashboard.walletBalance", { currency: mainWallet?.currency ?? netWorth.base_currency });

  return (
    <div className="easyb-page">
      <div className="easyb-col">
        <div className="easyb-card easyb-hero">
          <div className="easyb-hero-blob easyb-blob-1" />
          <div className="easyb-hero-blob easyb-blob-2" />
          <div className="easyb-hero-top">
            <div className="easyb-eyebrow light">{heroLabel}</div>
            <div className="easyb-hero-amount">
              {hidden ? "••••••" : (heroAmount ?? "—")}
              <button className="easyb-icon-btn" onClick={() => setHidden((h) => !h)} aria-label={t("dashboard.toggleBalanceVisibility")}>
                {hidden ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {netWorth && netWorth.wallets.length > 1 && (
              <button
                type="button"
                onClick={() => setShowTotal((v) => !v)}
                style={{
                  background: "none",
                  border: "none",
                  padding: 0,
                  marginTop: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  color: "rgba(255, 255, 255, 0.75)",
                  textDecoration: "underline",
                  cursor: "pointer",
                }}
              >
                {showTotal ? t("dashboard.showMainWalletOnly") : t("dashboard.showTotalAcrossWallets")}
              </button>
            )}
          </div>
          <div className="easyb-hero-wallets">
            {netWorth?.wallets
              .filter((wallet) => wallet.is_main || Number(wallet.available_balance) !== 0)
              .map((wallet) => (
              <button
                type="button"
                key={wallet.wallet_id}
                onClick={() => setMainWallet(wallet.wallet_id)}
                disabled={wallet.is_main || settingMainId === wallet.wallet_id}
                title={wallet.is_main ? t("dashboard.mainWallet") : t("dashboard.setAsMainWallet")}
                style={{
                  background: "rgba(255, 255, 255, 0.1)",
                  border: "1px solid rgba(255, 255, 255, 0.14)",
                  borderRadius: 999,
                  padding: "7px 14px",
                  fontSize: 13,
                  fontWeight: 400,
                  fontFamily: "inherit",
                  color: "inherit",
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  cursor: wallet.is_main || settingMainId ? "default" : "pointer",
                }}
              >
                <span className="easyb-hero-wallet-code">
                  {wallet.currency}
                  {wallet.is_main ? ` · ${t("dashboard.main")}` : ""}
                </span>
                <span>{hidden ? "••••" : wallet.available_balance}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="easyb-quick-actions">
          {quickActions.map((action) => (
            <Link className="easyb-quick-action" to={action.to} key={action.to}>
              <span className="easyb-quick-icon">
                <action.icon size={18} />
              </span>
              <span className="easyb-quick-label">{t(action.labelKey)}</span>
              <span className="easyb-quick-sub">{t(action.subKey)}</span>
            </Link>
          ))}
        </div>

        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>{t("dashboard.recentTransactions")}</h2>
            <Link className="easyb-link-btn" to="/transactions">
              {t("dashboard.viewAll")} <ChevronRight size={15} />
            </Link>
          </div>
          <div className="easyb-tx-list">
            {recentTransactions.map((transaction) => {
              const { sign, text } = formatAmount(transaction, userWalletIds);
              const typeLabel = formatTransactionType(transaction, userWalletIds, t);
              return (
                <div className="easyb-tx-row" key={transaction.id}>
                  <div className="easyb-tx-left">
                    <span className="easyb-cat-dot" style={{ background: colorForType(transaction.type) }}>
                      {sign === "+" ? <ArrowDownRight size={15} /> : <ArrowUpRight size={15} />}
                    </span>
                    <div>
                      <div className="easyb-tx-name">{transaction.description ?? transaction.type}</div>
                      <div className="easyb-tx-meta">
                        {new Date(transaction.created_at).toLocaleDateString()} · {typeLabel}
                      </div>
                    </div>
                  </div>
                  <div className="easyb-tx-right">
                    <span className={`easyb-chip ${STATUS_CHIP[transaction.status] ?? "easyb-chip-neutral"}`}>
                      {t(`common.status.${transaction.status}`, { defaultValue: transaction.status })}
                    </span>
                    <span className={`easyb-tx-amount ${sign === "+" ? "up" : ""}`}>
                      {sign}
                      {text}
                    </span>
                  </div>
                </div>
              );
            })}
            {recentTransactions.length === 0 && <p className="easyb-tx-meta">{t("dashboard.noTransactionsYet")}</p>}
          </div>
        </div>
      </div>

      <div className="easyb-col">
        <div className="easyb-card">
          <div className="easyb-section-header">
            <div>
              <div className="easyb-eyebrow">{t("dashboard.thisPeriod")}</div>
              <h2>{t("dashboard.spendingByType")}</h2>
            </div>
            <PeriodSelect />
          </div>
          {donutData.length > 0 ? (
            <>
              <div className="easyb-donut-wrap">
                <ResponsiveContainer width="100%" height={150}>
                  <PieChart>
                    <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={68} paddingAngle={2} stroke="none">
                      {donutData.map((item) => (
                        <Cell key={item.key} fill={item.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number, name: string) => [`${value.toFixed(2)} ${spendingCurrency ?? ""}`, name]}
                      // Pin the vertical position above the donut (x still
                      // follows the cursor) so the tooltip never lands on
                      // top of the fixed center total/currency overlay.
                      position={{ y: 0 }}
                      allowEscapeViewBox={{ x: true, y: true }}
                      contentStyle={{ borderRadius: 10, border: "1px solid var(--easyb-border)", fontSize: 12 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="easyb-donut-center">
                  <div className="easyb-donut-total">{spendingTotal.toFixed(0)}</div>
                  <div className="easyb-donut-label">{spendingCurrency ?? ""}</div>
                </div>
              </div>
              <div className="easyb-legend">
                {donutData.map((item) => (
                  <div className="easyb-legend-row" key={item.key}>
                    <span className="easyb-legend-dot" style={{ background: item.color }} />
                    <span className="easyb-legend-name">{item.name}</span>
                    <span className="easyb-legend-pct">
                      {spendingTotal > 0 ? Math.round((item.value / spendingTotal) * 100) : 0}%
                    </span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="easyb-tx-meta">{t("dashboard.noCompletedTransactions")}</p>
          )}
        </div>

        {isBusiness ? (
          <>
            <div className="easyb-card">
              <div className="easyb-section-header">
                <div>
                  <div className="easyb-eyebrow">{t("dashboard.thisPeriod")}</div>
                  <h2>{t("dashboard.cashFlow")}</h2>
                </div>
              </div>
              <div className="wallet-grid">
                <div className="wallet-chip">
                  <div className="wallet-chip__ccy">
                    <TrendingUp size={14} /> {t("dashboard.moneyIn")}
                  </div>
                  <div className="wallet-chip__amount" style={{ color: "var(--easyb-green)" }}>
                    +{monthCashFlow.incoming.toFixed(2)} {spendingCurrency ?? ""}
                  </div>
                </div>
                <div className="wallet-chip">
                  <div className="wallet-chip__ccy">
                    <TrendingDown size={14} /> {t("dashboard.moneyOut")}
                  </div>
                  <div className="wallet-chip__amount" style={{ color: "var(--easyb-red)" }}>
                    -{monthCashFlow.outgoing.toFixed(2)} {spendingCurrency ?? ""}
                  </div>
                </div>
                <div className="wallet-chip">
                  <div className="wallet-chip__ccy">{t("dashboard.netCashFlow")}</div>
                  <div
                    className="wallet-chip__amount"
                    style={{ color: netCashFlow >= 0 ? "var(--easyb-green)" : "var(--easyb-red)" }}
                  >
                    {netCashFlow >= 0 ? "+" : ""}
                    {netCashFlow.toFixed(2)} {spendingCurrency ?? ""}
                  </div>
                </div>
              </div>
            </div>

            <div className="easyb-card">
              <div className="easyb-section-header">
                <h2>{t("dashboard.upcomingPayments")}</h2>
                <Link className="easyb-link-btn" to="/payments?tab=scheduled">
                  {t("dashboard.viewAll")} <ChevronRight size={15} />
                </Link>
              </div>
              <div className="easyb-tx-list">
                {upcomingScheduledPayments.map((payment) => (
                  <div className="easyb-tx-row" key={payment.id}>
                    <div className="easyb-tx-left">
                      <div>
                        <div className="easyb-tx-name">{payment.beneficiary_name}</div>
                        <div className="easyb-tx-meta">
                          {new Date(`${payment.next_run_on}T00:00:00`).toLocaleDateString()}
                        </div>
                      </div>
                    </div>
                    <span className="easyb-tx-amount">
                      {payment.amount} {payment.currency}
                    </span>
                  </div>
                ))}
                {upcomingScheduledPayments.length === 0 && (
                  <p className="easyb-tx-meta">{t("dashboard.noUpcomingPayments")}</p>
                )}
              </div>
            </div>
          </>
        ) : (
          creditScore && (
            <div className="easyb-card">
              <div className="easyb-section-header">
                <h2>{t("dashboard.creditScore")}</h2>
              </div>
              <div className="easyb-score-wrap">
                <div className="easyb-ring" style={{ background: `conic-gradient(var(--easyb-accent) ${scorePercent * 3.6}deg, var(--easyb-border) 0deg)` }}>
                  <div className="easyb-ring-hole">
                    <div className="easyb-score-num">{creditScore.score}</div>
                    <div className="easyb-score-tag">{formatCreditBand(creditScore.band, t)}</div>
                  </div>
                </div>
                <div className="easyb-score-side">
                  <div className="easyb-score-line">{t("dashboard.outOf850")}</div>
                  <Link className="easyb-link-btn" to="/credit">
                    {t("dashboard.viewDetails")} <ChevronRight size={14} />
                  </Link>
                </div>
              </div>
            </div>
          )
        )}

        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>{t("dashboard.needsYourAttention")}</h2>
          </div>
          {needsAttention.length > 0 ? (
            <div className="easyb-attn-list">
              {needsAttention.map((transaction) => (
                <div className="easyb-attn-row" key={transaction.id}>
                  <span className="easyb-chip easyb-chip-violet">{t("dashboard.review")}</span>
                  <span className="easyb-attn-text">
                    {t("dashboard.onHoldPendingVerification", {
                      description: transaction.description ?? transaction.type,
                      amount: transaction.amount,
                      currency: transaction.currency,
                    })}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="easyb-tx-meta">{t("dashboard.nothingNeedsAttention")}</p>
          )}
        </div>
      </div>
    </div>
  );
}

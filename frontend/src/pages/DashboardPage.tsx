import {
  ArrowDownRight, ArrowUpRight, ChevronRight, Eye, EyeOff,
  Receipt, RefreshCcw, Send, Sparkles, type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { CreditScore, NetWorthResponse, SpendingByTypeResponse, Transaction } from "../types";

const QUICK_ACTIONS: { to: string; label: string; sub: string; icon: LucideIcon }[] = [
  { to: "/payments", label: "Send", sub: "New transfer", icon: Send },
  { to: "/wallets", label: "Convert", sub: "Exchange FX", icon: RefreshCcw },
  { to: "/transactions", label: "Review", sub: "All transactions", icon: Receipt },
  { to: "/assistant", label: "Ask", sub: "Assistant", icon: Sparkles },
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

function formatTransactionType(transaction: Transaction, userWalletIds: Set<string>): string {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  const description = transaction.description?.toLowerCase() ?? "";
  if (description.includes("loan") && description.includes("disbursement") && isIncoming && !isOutgoing) {
    return "Bank -> user";
  }
  if (transaction.type === "LOAN_PAYMENT") {
    return "User -> bank";
  }
  return transaction.type.replaceAll("_", " ");
}

export function DashboardPage() {
  const { user, accessToken } = useAuth();
  const [hidden, setHidden] = useState(false);
  const [netWorth, setNetWorth] = useState<NetWorthResponse | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [spending, setSpending] = useState<SpendingByTypeResponse | null>(null);
  const [creditScore, setCreditScore] = useState<CreditScore | null>(null);
  const [settingMainId, setSettingMainId] = useState<string | null>(null);
  const [showTotal, setShowTotal] = useState(false);

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
    apiRequest<SpendingByTypeResponse>("/analytics/spending-by-type", { token: accessToken })
      .then(setSpending)
      .catch(() => setSpending(null));
    apiRequest<CreditScore>("/credit/score", { token: accessToken })
      .then(setCreditScore)
      .catch(() => setCreditScore(null));
  }, [accessToken]);

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
    name: item.type,
    value: Number(item.total_amount),
    color: colorForType(item.type),
  }));

  const scorePercent = creditScore ? Math.min(100, Math.max(0, ((creditScore.score - 300) / 550) * 100)) : 0;

  const mainWallet = netWorth?.wallets.find((wallet) => wallet.is_main);
  const heroAmount = showTotal ? netWorth?.total_available_balance : mainWallet?.available_balance;
  const heroLabel = !netWorth
    ? `Welcome, ${user?.first_name}`
    : showTotal
      ? `Total balance · all wallets (${netWorth.base_currency})`
      : `${mainWallet?.currency ?? netWorth.base_currency} wallet balance`;

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
              <button className="easyb-icon-btn" onClick={() => setHidden((h) => !h)} aria-label="Toggle balance visibility">
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
                {showTotal ? "Show main wallet only" : "Show total across all wallets"}
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
                title={wallet.is_main ? "Main wallet" : "Set as main wallet"}
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
                  {wallet.is_main ? " · main" : ""}
                </span>
                <span>{hidden ? "••••" : wallet.available_balance}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="easyb-quick-actions">
          {QUICK_ACTIONS.map((action) => (
            <Link className="easyb-quick-action" to={action.to} key={action.to}>
              <span className="easyb-quick-icon">
                <action.icon size={18} />
              </span>
              <span className="easyb-quick-label">{action.label}</span>
              <span className="easyb-quick-sub">{action.sub}</span>
            </Link>
          ))}
        </div>

        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>Recent transactions</h2>
            <Link className="easyb-link-btn" to="/transactions">
              View all <ChevronRight size={15} />
            </Link>
          </div>
          <div className="easyb-tx-list">
            {recentTransactions.map((transaction) => {
              const { sign, text } = formatAmount(transaction, userWalletIds);
              const typeLabel = formatTransactionType(transaction, userWalletIds);
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
                      {transaction.status}
                    </span>
                    <span className={`easyb-tx-amount ${sign === "+" ? "up" : ""}`}>
                      {sign}
                      {text}
                    </span>
                  </div>
                </div>
              );
            })}
            {recentTransactions.length === 0 && <p className="easyb-tx-meta">No transactions yet.</p>}
          </div>
        </div>
      </div>

      <div className="easyb-col">
        <div className="easyb-card">
          <div className="easyb-section-header">
            <div>
              <div className="easyb-eyebrow">This period</div>
              <h2>Spending by type</h2>
            </div>
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
                    <Tooltip formatter={(value: number, name: string) => [`${value.toFixed(2)} ${spendingCurrency ?? ""}`, name]} contentStyle={{ borderRadius: 10, border: "1px solid var(--easyb-border)", fontSize: 12 }} />
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
                    <span className="easyb-legend-name">{item.name.toLowerCase().replaceAll("_", " ")}</span>
                    <span className="easyb-legend-pct">
                      {spendingTotal > 0 ? Math.round((item.value / spendingTotal) * 100) : 0}%
                    </span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="easyb-tx-meta">No completed transactions this period yet.</p>
          )}
        </div>

        {creditScore && (
          <div className="easyb-card">
            <div className="easyb-section-header">
              <h2>Credit score</h2>
            </div>
            <div className="easyb-score-wrap">
              <div className="easyb-ring" style={{ background: `conic-gradient(var(--easyb-accent) ${scorePercent * 3.6}deg, var(--easyb-border) 0deg)` }}>
                <div className="easyb-ring-hole">
                  <div className="easyb-score-num">{creditScore.score}</div>
                  <div className="easyb-score-tag">{creditScore.band.replaceAll("_", " ")}</div>
                </div>
              </div>
              <div className="easyb-score-side">
                <div className="easyb-score-line">/ 850</div>
                <Link className="easyb-link-btn" to="/credit">
                  View details <ChevronRight size={14} />
                </Link>
              </div>
            </div>
          </div>
        )}

        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>Needs your attention</h2>
          </div>
          {needsAttention.length > 0 ? (
            <div className="easyb-attn-list">
              {needsAttention.map((transaction) => (
                <div className="easyb-attn-row" key={transaction.id}>
                  <span className="easyb-chip easyb-chip-violet">Review</span>
                  <span className="easyb-attn-text">
                    {transaction.description ?? transaction.type} · {transaction.amount} {transaction.currency} is on
                    hold pending verification.
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="easyb-tx-meta">Nothing needs your attention right now.</p>
          )}
        </div>
      </div>
    </div>
  );
}

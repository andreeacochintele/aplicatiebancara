import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Transaction, Wallet } from "../types";

const QUICK_ACTIONS = [
  { to: "/payments", eyebrow: "Send", label: "New transfer" },
  { to: "/wallets", eyebrow: "Exchange", label: "Convert FX" },
  { to: "/transactions", eyebrow: "Review", label: "All transactions" },
  { to: "/assistant", eyebrow: "Ask", label: "Assistant" },
];

function formatAmount(transaction: Transaction, userWalletIds: Set<string>): string {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  const sign = isIncoming && !isOutgoing ? "+" : "-";
  return `${sign}${transaction.amount} ${transaction.currency}`;
}

export function DashboardPage() {
  const { user, accessToken } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
    apiRequest<Transaction[]>("/transactions", { token: accessToken })
      .then((list) =>
        setTransactions(
          [...list].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5),
        ),
      )
      .catch(() => setTransactions([]));
  }, [accessToken]);

  const mainWallet = wallets.find((wallet) => wallet.is_main) ?? wallets[0];
  const userWalletIds = new Set(wallets.map((wallet) => wallet.id));

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="eyebrow">
          {mainWallet ? `Main wallet · ${mainWallet.currency}` : `Welcome, ${user?.first_name}`}
        </div>
        {mainWallet && <div className="balance-hero__amount">{mainWallet.available_balance}</div>}
        <div className="wallet-grid">
          {wallets.map((wallet) => (
            <div className="wallet-chip" key={wallet.id}>
              <div className="wallet-chip__ccy">
                {wallet.currency}
                {wallet.is_main && <span className="tag tag--accent">MAIN</span>}
              </div>
              <div className="wallet-chip__amount">{wallet.available_balance}</div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: "0.6rem" }}>
          Quick actions
        </div>
        <div className="quick-actions">
          {QUICK_ACTIONS.map((action) => (
            <Link className="quick-action" to={action.to} key={action.to}>
              <span className="eyebrow">{action.eyebrow}</span>
              {action.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Recent transactions</span>
          <Link to="/transactions">View all</Link>
        </div>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Type</th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((transaction) => (
              <tr key={transaction.id}>
                <td>{new Date(transaction.created_at).toLocaleDateString()}</td>
                <td>{transaction.description ?? "—"}</td>
                <td>{transaction.type}</td>
                <td>
                  <span className="tag tag--neutral">{transaction.status}</span>
                </td>
                <td style={{ textAlign: "right" }}>{formatAmount(transaction, userWalletIds)}</td>
              </tr>
            ))}
            {transactions.length === 0 && (
              <tr>
                <td colSpan={5}>No transactions yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

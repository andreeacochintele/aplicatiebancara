import { useEffect, useState } from "react";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Transaction, Wallet } from "../types";

function formatAmount(transaction: Transaction, userWalletIds: Set<string>): string {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  const sign = isIncoming && !isOutgoing ? "+" : "-";
  return `${sign}${transaction.amount} ${transaction.currency}`;
}

export function TransactionsPage() {
  const { accessToken } = useAuth();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Transaction[]>("/transactions", { token: accessToken })
      .then(setTransactions)
      .catch(() => setTransactions([]));
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
  }, [accessToken]);

  const userWalletIds = new Set(wallets.map((wallet) => wallet.id));

  return (
    <section>
      <h2>Transactions</h2>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Description</th>
            <th>Amount</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => (
            <tr key={tx.id}>
              <td>{new Date(tx.created_at).toLocaleString()}</td>
              <td>{tx.type}</td>
              <td>{tx.description}</td>
              <td>{formatAmount(tx, userWalletIds)}</td>
              <td>{tx.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

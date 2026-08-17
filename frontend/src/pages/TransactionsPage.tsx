import { useEffect, useState } from "react";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Transaction } from "../types";

export function TransactionsPage() {
  const { accessToken } = useAuth();
  const [transactions, setTransactions] = useState<Transaction[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Transaction[]>("/transactions", { token: accessToken })
      .then(setTransactions)
      .catch(() => setTransactions([]));
  }, [accessToken]);

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
              <td>
                {tx.amount} {tx.currency}
              </td>
              <td>{tx.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

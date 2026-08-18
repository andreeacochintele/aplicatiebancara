import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Statement, Wallet } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

function todayMinus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function StatementsPage() {
  const { accessToken } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [walletId, setWalletId] = useState("");
  const [dateFrom, setDateFrom] = useState(todayMinus(30));
  const [dateTo, setDateTo] = useState(todayMinus(0));
  const [statement, setStatement] = useState<Statement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then((list) => {
      setWallets(list);
      if (list.length > 0) setWalletId((list.find((w) => w.is_main) ?? list[0]).id);
    });
  }, [accessToken]);

  async function generate() {
    if (!accessToken || !walletId) return;
    setError(null);
    setBusy(true);
    try {
      const params = new URLSearchParams({ wallet_id: walletId, date_from: dateFrom, date_to: dateTo });
      const data = await apiRequest<Statement>(`/statements?${params.toString()}`, { token: accessToken });
      setStatement(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate statement");
    } finally {
      setBusy(false);
    }
  }

  async function exportFile(format: "csv" | "pdf") {
    if (!accessToken || !walletId) return;
    const params = new URLSearchParams({ wallet_id: walletId, date_from: dateFrom, date_to: dateTo, format });
    const response = await fetch(`${API_BASE_URL}/statements/export?${params.toString()}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      setError("Export failed");
      return;
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `statement_${dateFrom}_${dateTo}.${format}`;
    link.click();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile" style={{ maxWidth: 560 }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <label style={{ flex: 1 }}>
            Wallet
            <select value={walletId} onChange={(e) => setWalletId(e.target.value)}>
              {wallets.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.currency} {w.is_main ? "(main)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label style={{ flex: 1 }}>
            From
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label style={{ flex: 1 }}>
            To
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
        </div>
        <button onClick={generate} disabled={busy || !walletId} style={{ marginTop: "0.75rem" }}>
          Generate
        </button>
        {error && <p role="alert">{error}</p>}
      </div>

      {statement && (
        <div className="tile">
          <div className="tile__header">
            <span className="eyebrow">
              {statement.currency} · {statement.date_from} → {statement.date_to}
            </span>
            <div style={{ display: "flex", gap: "0.5rem", marginLeft: "auto" }}>
              <button onClick={() => exportFile("csv")}>Export CSV</button>
              <button onClick={() => exportFile("pdf")}>Export PDF</button>
            </div>
          </div>

          <div className="wallet-grid" style={{ marginBottom: "1rem" }}>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">Opening balance</div>
              <div className="wallet-chip__amount">{statement.opening_balance}</div>
            </div>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">Closing balance</div>
              <div className="wallet-chip__amount">{statement.closing_balance}</div>
            </div>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">Total incoming</div>
              <div className="wallet-chip__amount">{statement.total_incoming}</div>
            </div>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">Total outgoing</div>
              <div className="wallet-chip__amount">{statement.total_outgoing}</div>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Type</th>
                <th>Direction</th>
                <th style={{ textAlign: "right" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {statement.transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{new Date(tx.created_at).toLocaleDateString()}</td>
                  <td>{tx.description ?? "—"}</td>
                  <td>{tx.type}</td>
                  <td>
                    <span className={`tag ${tx.direction === "IN" ? "tag--accent" : "tag--neutral"}`}>
                      {tx.direction}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>{tx.amount}</td>
                </tr>
              ))}
              {statement.transactions.length === 0 && (
                <tr>
                  <td colSpan={5}>No activity in this period.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

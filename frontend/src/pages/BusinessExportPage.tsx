import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

interface BusinessExportRow {
  date: string;
  transaction_id: string;
  type: string;
  counterparty: string;
  description: string | null;
  category: string | null;
  amount: string;
  currency: string;
  status: string;
}

interface CurrencyTotal {
  currency: string;
  total_incoming: string;
  total_outgoing: string;
}

interface BusinessExportPreview {
  date_from: string;
  date_to: string;
  row_count: number;
  totals: CurrencyTotal[];
  transactions: BusinessExportRow[];
}

interface ExportJob {
  id: string;
  format: "CSV" | "XLSX" | "PDF";
  date_from: string;
  date_to: string;
  status: string;
  row_count: number;
  created_at: string;
}

function todayMinus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

async function downloadBlob(response: Response, fallbackName: string) {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = match?.[1] ?? fallbackName;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

export function BusinessExportPage() {
  const { user, accessToken } = useAuth();
  const [dateFrom, setDateFrom] = useState(todayMinus(30));
  const [dateTo, setDateTo] = useState(todayMinus(0));
  const [direction, setDirection] = useState<"" | "incoming" | "outgoing">("");
  const [format, setFormat] = useState<"csv" | "xlsx">("csv");
  const [preview, setPreview] = useState<BusinessExportPreview | null>(null);
  const [history, setHistory] = useState<ExportJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isBusiness = user?.user_type === "BUSINESS";

  useEffect(() => {
    if (!isBusiness || !accessToken) return;
    loadHistory();
  }, [isBusiness, accessToken]);

  if (!isBusiness) {
    return (
      <section className="tile">
        <p>Transaction export is only available to business accounts.</p>
      </section>
    );
  }

  function buildParams(extra?: Record<string, string>) {
    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, ...extra });
    if (direction) params.set("direction", direction);
    return params;
  }

  async function loadHistory() {
    if (!accessToken) return;
    try {
      const jobs = await apiRequest<ExportJob[]>("/exports", { token: accessToken });
      setHistory(jobs);
    } catch {
      setHistory([]);
    }
  }

  async function generatePreview() {
    if (!accessToken) return;
    setError(null);
    setBusy(true);
    try {
      const data = await apiRequest<BusinessExportPreview>(`/exports/preview?${buildParams().toString()}`, {
        token: accessToken,
      });
      setPreview(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate preview");
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    if (!accessToken) return;
    setError(null);
    setBusy(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/exports/transactions?${buildParams({ format }).toString()}`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
      );
      if (!response.ok) {
        setError("Export failed");
        return;
      }
      await downloadBlob(response, `transactions_${dateFrom}_${dateTo}.${format}`);
      await loadHistory();
    } finally {
      setBusy(false);
    }
  }

  async function redownload(job: ExportJob) {
    if (!accessToken) return;
    const response = await fetch(`${API_BASE_URL}/exports/${job.id}/download`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      setError("Could not re-download this export");
      return;
    }
    await downloadBlob(response, `transactions_${job.date_from}_${job.date_to}.${job.format.toLowerCase()}`);
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile" style={{ maxWidth: 620 }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <label style={{ flex: 1 }}>
            From
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label style={{ flex: 1 }}>
            To
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <label style={{ flex: 1 }}>
            Direction
            <select value={direction} onChange={(e) => setDirection(e.target.value as "" | "incoming" | "outgoing")}>
              <option value="">All</option>
              <option value="incoming">Incoming</option>
              <option value="outgoing">Outgoing</option>
            </select>
          </label>
          <label style={{ flex: 1 }}>
            Format
            <select value={format} onChange={(e) => setFormat(e.target.value as "csv" | "xlsx")}>
              <option value="csv">CSV</option>
              <option value="xlsx">XLSX</option>
            </select>
          </label>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
          <button onClick={generatePreview} disabled={busy}>
            Preview
          </button>
          <button onClick={download} disabled={busy}>
            Export {format.toUpperCase()}
          </button>
        </div>
        {error && <p role="alert">{error}</p>}
      </div>

      {preview && (
        <div className="tile">
          <div className="tile__header">
            <span className="eyebrow">
              {preview.row_count} transactions &middot; {preview.date_from} &rarr; {preview.date_to}
            </span>
          </div>

          {preview.totals.length > 0 && (
            <div className="wallet-grid" style={{ marginBottom: "1rem" }}>
              {preview.totals.map((total) => (
                <div className="wallet-chip" key={total.currency}>
                  <div className="wallet-chip__ccy">{total.currency}</div>
                  <div className="wallet-chip__amount">+{total.total_incoming}</div>
                  <div style={{ fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
                    -{total.total_outgoing}
                  </div>
                </div>
              ))}
            </div>
          )}

          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Counterparty</th>
                <th>Category</th>
                <th style={{ textAlign: "right" }}>Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {preview.transactions.map((row) => (
                <tr key={row.transaction_id}>
                  <td>{new Date(row.date).toLocaleDateString()}</td>
                  <td>{row.type}</td>
                  <td>{row.counterparty || row.description || "—"}</td>
                  <td>{row.category ?? "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    {row.amount} {row.currency}
                  </td>
                  <td>
                    <span className="tag tag--neutral">{row.status}</span>
                  </td>
                </tr>
              ))}
              {preview.transactions.length === 0 && (
                <tr>
                  <td colSpan={6}>No transactions in this period.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Export history</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Generated</th>
              <th>Period</th>
              <th>Format</th>
              <th>Rows</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {history.map((job) => (
              <tr key={job.id}>
                <td>{new Date(job.created_at).toLocaleString()}</td>
                <td>
                  {job.date_from} &rarr; {job.date_to}
                </td>
                <td>{job.format}</td>
                <td>{job.row_count}</td>
                <td>
                  <span className="tag tag--accent">{job.status}</span>
                </td>
                <td>
                  <button onClick={() => redownload(job)}>Download</button>
                </td>
              </tr>
            ))}
            {history.length === 0 && (
              <tr>
                <td colSpan={6}>No exports generated yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

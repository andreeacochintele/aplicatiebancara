import { useState } from "react";

import { useAuth } from "../hooks/useAuth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

function todayMinus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function BusinessExportPage() {
  const { user, accessToken } = useAuth();
  const [dateFrom, setDateFrom] = useState(todayMinus(30));
  const [dateTo, setDateTo] = useState(todayMinus(0));
  const [direction, setDirection] = useState<"" | "incoming" | "outgoing">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user?.user_type !== "BUSINESS") {
    return (
      <section className="tile">
        <p>Transaction export is only available to business accounts.</p>
      </section>
    );
  }

  async function downloadCsv() {
    if (!accessToken) return;
    setError(null);
    setBusy(true);
    try {
      const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      if (direction) params.set("direction", direction);
      const response = await fetch(`${API_BASE_URL}/exports/transactions?${params.toString()}`, {
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
      link.download = `transactions_${dateFrom}_${dateTo}.csv`;
      link.click();
      URL.revokeObjectURL(objectUrl);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="tile" style={{ maxWidth: 560 }}>
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
      </div>
      <button onClick={downloadCsv} disabled={busy} style={{ marginTop: "0.75rem" }}>
        Export CSV
      </button>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

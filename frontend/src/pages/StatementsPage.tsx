import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Statement, Wallet } from "../types";
import { downloadBlob, walletLabel } from "../utils";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const STATEMENT_ROWS_PER_PAGE = 15;
const STATEMENT_HISTORY_PER_PAGE = 10;

interface StatementExportJob {
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

export function StatementsPage() {
  const { t } = useTranslation();
  const { accessToken } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [walletId, setWalletId] = useState("");
  const [dateFrom, setDateFrom] = useState(todayMinus(30));
  const [dateTo, setDateTo] = useState(todayMinus(0));
  const [statement, setStatement] = useState<Statement | null>(null);
  const [history, setHistory] = useState<StatementExportJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [transactionsPage, setTransactionsPage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);

  useEffect(() => {
    setTransactionsPage((currentPage) => {
      const maxPage = Math.max(1, Math.ceil((statement?.transactions.length ?? 0) / STATEMENT_ROWS_PER_PAGE));
      return Math.min(currentPage, maxPage);
    });
  }, [statement]);

  useEffect(() => {
    setHistoryPage((currentPage) => {
      const maxPage = Math.max(1, Math.ceil(history.length / STATEMENT_HISTORY_PER_PAGE));
      return Math.min(currentPage, maxPage);
    });
  }, [history.length]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then((list) => {
      setWallets(list);
      if (list.length > 0) setWalletId((list.find((w) => w.is_main) ?? list[0]).id);
    });
    loadHistory();
  }, [accessToken]);

  async function loadHistory() {
    if (!accessToken) return;
    try {
      const jobs = await apiRequest<StatementExportJob[]>("/statements/history", { token: accessToken });
      setHistory(jobs);
    } catch {
      setHistory([]);
    }
  }

  async function generate() {
    if (!accessToken || !walletId) return;
    setError(null);
    setStatement(null);
    setBusy(true);
    try {
      const params = new URLSearchParams({ wallet_id: walletId, date_from: dateFrom, date_to: dateTo });
      const data = await apiRequest<Statement>(`/statements?${params.toString()}`, { token: accessToken });
      setStatement(data);
      setTransactionsPage(1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("statements.couldNotGenerate"));
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
      setError(t("statements.exportFailed"));
      return;
    }
    await downloadBlob(response, `statement_${dateFrom}_${dateTo}.${format}`);
    await loadHistory();
  }

  async function redownload(job: StatementExportJob) {
    if (!accessToken) return;
    const response = await fetch(`${API_BASE_URL}/statements/history/${job.id}/download`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      setError(t("statements.couldNotRedownload"));
      return;
    }
    await downloadBlob(response, `statement_${job.date_from}_${job.date_to}.${job.format.toLowerCase()}`);
  }

  const statementTransactions = statement?.transactions ?? [];
  const transactionPageCount = Math.max(1, Math.ceil(statementTransactions.length / STATEMENT_ROWS_PER_PAGE));
  const currentTransactionsPage = Math.min(transactionsPage, transactionPageCount);
  const transactionsPageStart = (currentTransactionsPage - 1) * STATEMENT_ROWS_PER_PAGE;
  const visibleTransactions = statementTransactions.slice(transactionsPageStart, transactionsPageStart + STATEMENT_ROWS_PER_PAGE);
  const firstVisibleTransaction = statementTransactions.length === 0 ? 0 : transactionsPageStart + 1;
  const lastVisibleTransaction = Math.min(transactionsPageStart + STATEMENT_ROWS_PER_PAGE, statementTransactions.length);
  const transactionPageButtonCount = Math.min(5, transactionPageCount);
  const firstTransactionPageButton = Math.min(
    Math.max(1, currentTransactionsPage - 2),
    Math.max(1, transactionPageCount - transactionPageButtonCount + 1),
  );
  const transactionPageNumbers = Array.from(
    { length: transactionPageButtonCount },
    (_, index) => firstTransactionPageButton + index,
  );

  const historyPageCount = Math.max(1, Math.ceil(history.length / STATEMENT_HISTORY_PER_PAGE));
  const currentHistoryPage = Math.min(historyPage, historyPageCount);
  const historyPageStart = (currentHistoryPage - 1) * STATEMENT_HISTORY_PER_PAGE;
  const visibleHistory = history.slice(historyPageStart, historyPageStart + STATEMENT_HISTORY_PER_PAGE);
  const firstVisibleHistory = history.length === 0 ? 0 : historyPageStart + 1;
  const lastVisibleHistory = Math.min(historyPageStart + STATEMENT_HISTORY_PER_PAGE, history.length);
  const historyPageButtonCount = Math.min(5, historyPageCount);
  const firstHistoryPageButton = Math.min(
    Math.max(1, currentHistoryPage - 2),
    Math.max(1, historyPageCount - historyPageButtonCount + 1),
  );
  const historyPageNumbers = Array.from({ length: historyPageButtonCount }, (_, index) => firstHistoryPageButton + index);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile" style={{ maxWidth: 560 }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <label style={{ flex: 1 }}>
            {t("statements.wallet")}
            <select value={walletId} onChange={(e) => setWalletId(e.target.value)}>
              {wallets.map((w) => (
                <option key={w.id} value={w.id}>
                  {walletLabel(w)} {w.is_main ? t("statements.main") : ""}
                </option>
              ))}
            </select>
          </label>
          <label style={{ flex: 1 }}>
            {t("statements.from")}
            <input type="date" value={dateFrom} max={dateTo} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label style={{ flex: 1 }}>
            {t("statements.to")}
            <input type="date" value={dateTo} min={dateFrom} onChange={(e) => setDateTo(e.target.value)} />
          </label>
        </div>
        <button onClick={generate} disabled={busy || !walletId} style={{ marginTop: "0.75rem" }}>
          {t("statements.generate")}
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
              <button onClick={() => exportFile("csv")}>{t("statements.exportCsv")}</button>
              <button onClick={() => exportFile("pdf")}>{t("statements.exportPdf")}</button>
            </div>
          </div>

          <div className="wallet-grid" style={{ marginBottom: "1rem" }}>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">{t("statements.openingBalance")}</div>
              <div className="wallet-chip__amount">{statement.opening_balance}</div>
            </div>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">{t("statements.closingBalance")}</div>
              <div className="wallet-chip__amount">{statement.closing_balance}</div>
            </div>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">{t("statements.totalIncoming")}</div>
              <div className="wallet-chip__amount">{statement.total_incoming}</div>
            </div>
            <div className="wallet-chip">
              <div className="wallet-chip__ccy">{t("statements.totalOutgoing")}</div>
              <div className="wallet-chip__amount">{statement.total_outgoing}</div>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>{t("statements.date")}</th>
                <th>{t("statements.transactionId")}</th>
                <th>{t("statements.description")}</th>
                <th>{t("statements.type")}</th>
                <th>{t("statements.direction")}</th>
                <th style={{ textAlign: "right" }}>{t("statements.amount")}</th>
              </tr>
            </thead>
            <tbody>
              {visibleTransactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{new Date(tx.created_at).toLocaleDateString()}</td>
                  <td title={tx.id}>{tx.id.slice(0, 8)}</td>
                  <td>{tx.description ?? "—"}</td>
                  <td>{t(`common.txType.${tx.type}`, { defaultValue: tx.type })}</td>
                  <td>
                    <span className={`tag ${tx.direction === "IN" ? "tag--accent" : "tag--neutral"}`}>
                      {tx.direction}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>{tx.amount}</td>
                </tr>
              ))}
              {statementTransactions.length === 0 && (
                <tr>
                  <td colSpan={6}>{t("statements.noActivity")}</td>
                </tr>
              )}
            </tbody>
          </table>
          {statementTransactions.length > STATEMENT_ROWS_PER_PAGE && (
            <div
              style={{
                alignItems: "center",
                display: "flex",
                flexWrap: "wrap",
                gap: "0.6rem",
                justifyContent: "space-between",
                marginTop: "1rem",
              }}
            >
              <span className="eyebrow">
                {t("statements.showingRange", {
                  first: firstVisibleTransaction,
                  last: lastVisibleTransaction,
                  total: statementTransactions.length,
                })}
              </span>
              <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                <button
                  type="button"
                  className="button--ghost"
                  aria-label={t("statements.previousPage")}
                  disabled={currentTransactionsPage === 1}
                  onClick={() => setTransactionsPage((value) => Math.max(1, value - 1))}
                  style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
                >
                  <ChevronLeft size={16} aria-hidden="true" />
                </button>
                {transactionPageNumbers.map((pageNumber) => (
                  <button
                    key={pageNumber}
                    type="button"
                    className={pageNumber === currentTransactionsPage ? undefined : "button--ghost"}
                    aria-label={t("statements.goToPage", { page: pageNumber })}
                    aria-current={pageNumber === currentTransactionsPage ? "page" : undefined}
                    onClick={() => setTransactionsPage(pageNumber)}
                    style={{ minWidth: 40, padding: "0.65rem 0.75rem" }}
                  >
                    {pageNumber}
                  </button>
                ))}
                <button
                  type="button"
                  className="button--ghost"
                  aria-label={t("statements.nextPage")}
                  disabled={currentTransactionsPage === transactionPageCount}
                  onClick={() => setTransactionsPage((value) => Math.min(transactionPageCount, value + 1))}
                  style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
                >
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("statements.statementHistory")}</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>{t("statements.generated")}</th>
              <th>{t("statements.period")}</th>
              <th>{t("statements.format")}</th>
              <th>{t("statements.rows")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visibleHistory.map((job) => (
              <tr key={job.id}>
                <td>{new Date(job.created_at).toLocaleString()}</td>
                <td>
                  {job.date_from} &rarr; {job.date_to}
                </td>
                <td>{job.format}</td>
                <td>{job.row_count}</td>
                <td>
                  <button onClick={() => redownload(job)}>{t("statements.download")}</button>
                </td>
              </tr>
            ))}
            {history.length === 0 && (
              <tr>
                <td colSpan={5}>{t("statements.noStatementsGenerated")}</td>
              </tr>
            )}
          </tbody>
        </table>
        {history.length > STATEMENT_HISTORY_PER_PAGE && (
          <div
            style={{
              alignItems: "center",
              display: "flex",
              flexWrap: "wrap",
              gap: "0.6rem",
              justifyContent: "space-between",
              marginTop: "1rem",
            }}
          >
            <span className="eyebrow">
              {t("statements.showingHistoryRange", {
                first: firstVisibleHistory,
                last: lastVisibleHistory,
                total: history.length,
              })}
            </span>
            <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
              <button
                type="button"
                className="button--ghost"
                aria-label={t("statements.previousHistoryPage")}
                disabled={currentHistoryPage === 1}
                onClick={() => setHistoryPage((value) => Math.max(1, value - 1))}
                style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
              >
                <ChevronLeft size={16} aria-hidden="true" />
              </button>
              {historyPageNumbers.map((pageNumber) => (
                <button
                  key={pageNumber}
                  type="button"
                  className={pageNumber === currentHistoryPage ? undefined : "button--ghost"}
                  aria-label={t("statements.goToHistoryPage", { page: pageNumber })}
                  aria-current={pageNumber === currentHistoryPage ? "page" : undefined}
                  onClick={() => setHistoryPage(pageNumber)}
                  style={{ minWidth: 40, padding: "0.65rem 0.75rem" }}
                >
                  {pageNumber}
                </button>
              ))}
              <button
                type="button"
                className="button--ghost"
                aria-label={t("statements.nextHistoryPage")}
                disabled={currentHistoryPage === historyPageCount}
                onClick={() => setHistoryPage((value) => Math.min(historyPageCount, value + 1))}
                style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
              >
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

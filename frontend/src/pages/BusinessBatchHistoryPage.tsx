import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { BulkTransferBatchSummary, Transaction } from "../types";

export function BusinessBatchHistoryPage() {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const isBusiness = user?.user_type === "BUSINESS";

  const [history, setHistory] = useState<BulkTransferBatchSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [expandedBatchReference, setExpandedBatchReference] = useState<string | null>(null);
  const [batchRows, setBatchRows] = useState<Transaction[]>([]);
  const [batchRowsLoading, setBatchRowsLoading] = useState(false);

  async function loadHistory(token: string) {
    setHistoryLoading(true);
    try {
      const batches = await apiRequest<BulkTransferBatchSummary[]>("/payments/transfers/bulk/history", { token });
      setHistory(batches);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function toggleBatch(batch: BulkTransferBatchSummary) {
    if (expandedBatchReference === batch.batch_reference) {
      setExpandedBatchReference(null);
      return;
    }
    setExpandedBatchReference(batch.batch_reference);
    if (!accessToken) return;
    setBatchRowsLoading(true);
    try {
      const rows = await apiRequest<Transaction[]>(
        `/payments/transfers/bulk/history/${batch.batch_reference}`,
        { token: accessToken },
      );
      setBatchRows(rows);
    } catch {
      setBatchRows([]);
    } finally {
      setBatchRowsLoading(false);
    }
  }

  useEffect(() => {
    if (!isBusiness || !accessToken) return;
    void loadHistory(accessToken);
  }, [isBusiness, accessToken]);

  if (!isBusiness) {
    return (
      <section className="tile">
        <p>{t("businessBulkTransfer.onlyForBusiness")}</p>
      </section>
    );
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("businessBulkTransfer.historyTitle")}</span>
          {historyLoading && <span className="tag tag--neutral">{t("businessBulkTransfer.loading")}</span>}
        </div>
        <table>
          <thead>
            <tr>
              <th>{t("businessBulkTransfer.batchId")}</th>
              <th>{t("businessBulkTransfer.date")}</th>
              <th>{t("businessBulkTransfer.rows")}</th>
              <th style={{ textAlign: "right" }}>{t("businessBulkTransfer.amount")}</th>
              <th>{t("common.statusLabel")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {history.map((batch) => {
              const isExpanded = expandedBatchReference === batch.batch_reference;
              return (
                <Fragment key={batch.batch_reference}>
                  <tr>
                    <td>
                      <code title={batch.batch_reference}>{batch.batch_reference.slice(0, 8)}</code>
                    </td>
                    <td>{new Date(batch.created_at).toLocaleString()}</td>
                    <td>{batch.row_count}</td>
                    <td style={{ textAlign: "right" }}>
                      {batch.total_amount} {batch.currency}
                    </td>
                    <td>
                      {batch.pending_review_count > 0 ? (
                        <span className="tag tag--warning">
                          {t("businessBulkTransfer.batchPendingReview", { count: batch.pending_review_count })}
                        </span>
                      ) : batch.other_count > 0 ? (
                        <span className="tag tag--warning">{t("businessBulkTransfer.batchNeedsAttention")}</span>
                      ) : (
                        <span className="tag tag--accent">{t("businessBulkTransfer.batchAllCompleted")}</span>
                      )}
                    </td>
                    <td>
                      <button type="button" className="button--ghost" onClick={() => toggleBatch(batch)}>
                        {isExpanded ? " ▴" : " ▾"}
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr>
                      <td colSpan={6}>
                        {batchRowsLoading ? (
                          <span className="tag tag--neutral">{t("businessBulkTransfer.loading")}</span>
                        ) : (
                          <table>
                            <thead>
                              <tr>
                                <th>{t("businessBulkTransfer.description")}</th>
                                <th style={{ textAlign: "right" }}>{t("businessBulkTransfer.amount")}</th>
                                <th>{t("common.statusLabel")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {batchRows.map((row) => (
                                <tr key={row.id}>
                                  <td>{row.description ?? "—"}</td>
                                  <td style={{ textAlign: "right" }}>
                                    {row.amount} {row.currency}
                                  </td>
                                  <td>
                                    {t(`common.status.${row.status}`, { defaultValue: row.status })}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {!historyLoading && history.length === 0 && (
              <tr>
                <td colSpan={6}>{t("businessBulkTransfer.noHistoryYet")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

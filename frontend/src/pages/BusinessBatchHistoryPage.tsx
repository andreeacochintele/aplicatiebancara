import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { BulkTransferBatchSummary } from "../types";

export function BusinessBatchHistoryPage() {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const isBusiness = user?.user_type === "BUSINESS";

  const [history, setHistory] = useState<BulkTransferBatchSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

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
              <th>{t("businessBulkTransfer.date")}</th>
              <th>{t("businessBulkTransfer.rows")}</th>
              <th style={{ textAlign: "right" }}>{t("businessBulkTransfer.amount")}</th>
              <th>{t("common.statusLabel")}</th>
            </tr>
          </thead>
          <tbody>
            {history.map((batch) => (
              <tr key={batch.batch_reference}>
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
              </tr>
            ))}
            {!historyLoading && history.length === 0 && (
              <tr>
                <td colSpan={4}>{t("businessBulkTransfer.noHistoryYet")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

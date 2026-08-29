import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";

interface WalletDiscrepancy {
  wallet_id: string;
  user_id: string;
  currency: string;
  stored_total_balance: string;
  ledger_derived_balance: string;
  difference: string;
}

interface ReconciliationReport {
  wallets_checked: number;
  discrepancies: WalletDiscrepancy[];
}

export function ReconciliationPage() {
  const { t } = useTranslation();
  const { accessToken, logout, user } = useAuth();
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function runReconciliation() {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<ReconciliationReport>("/admin/reconciliation", { token: accessToken });
      setReport(response);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotRunReconciliation"));
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken || user?.role !== "ADMIN") {
      setLoading(false);
      return;
    }
    void runReconciliation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, user?.role]);

  if (user?.role !== "ADMIN") {
    return (
      <section className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.reconciliation")}</span>
        </div>
        <div className="card-empty">{t("admin.adminPrivilegesRequired")}</div>
      </section>
    );
  }

  const discrepancyCount = report?.discrepancies.length ?? 0;
  const isClean = report !== null && discrepancyCount === 0;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.reconciliation")}</span>
          <button type="button" className="button--ghost" onClick={() => void runReconciliation()} disabled={loading} style={{ marginLeft: "auto" }}>
            <RefreshCw size={14} style={{ verticalAlign: -2, marginRight: 4 }} aria-hidden="true" />
            {loading ? t("admin.checking") : t("admin.runAgain")}
          </button>
        </div>
        <p style={{ margin: 0, color: "var(--color-text-muted)" }}>{t("admin.reconciliationDescription")}</p>
      </div>

      {error && (
        <div className="tile">
          <p role="alert" style={{ color: "var(--color-warning)", margin: 0 }}>{error}</p>
        </div>
      )}

      {loading && !report && <div className="tile card-empty">{t("admin.checking")}</div>}

      {report && (
        <div className="tile">
          {isClean ? (
            <div
              style={{
                alignItems: "center",
                display: "flex",
                gap: "0.75rem",
                padding: "0.5rem 0",
              }}
            >
              <CheckCircle2 size={28} color="var(--color-success)" aria-hidden="true" />
              <div>
                <strong style={{ display: "block" }}>{t("admin.reconciliationClean")}</strong>
                <span style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
                  {t("admin.walletsCheckedCount", { count: report.wallets_checked })}
                </span>
              </div>
            </div>
          ) : (
            <>
              <div style={{ alignItems: "center", display: "flex", gap: "0.6rem", marginBottom: "0.85rem" }}>
                <AlertTriangle size={22} style={{ color: "var(--color-warning)" }} aria-hidden="true" />
                <strong>
                  {t("admin.discrepanciesFound", { count: discrepancyCount, total: report.wallets_checked })}
                </strong>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>{t("admin.wallet")}</th>
                    <th>{t("admin.userId")}</th>
                    <th>{t("admin.currency")}</th>
                    <th style={{ textAlign: "right" }}>{t("admin.storedBalance")}</th>
                    <th style={{ textAlign: "right" }}>{t("admin.ledgerBalance")}</th>
                    <th style={{ textAlign: "right" }}>{t("admin.difference")}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.discrepancies.map((d) => (
                    <tr key={d.wallet_id}>
                      <td title={d.wallet_id}>{d.wallet_id.slice(0, 8)}</td>
                      <td title={d.user_id}>{d.user_id.slice(0, 8)}</td>
                      <td>{d.currency}</td>
                      <td style={{ textAlign: "right" }}>{d.stored_total_balance}</td>
                      <td style={{ textAlign: "right" }}>{d.ledger_derived_balance}</td>
                      <td style={{ textAlign: "right", color: "var(--color-warning)", fontWeight: 600 }}>
                        {d.difference}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </section>
  );
}

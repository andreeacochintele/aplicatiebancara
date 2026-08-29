import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type { AdminAuditLog } from "../../types";

const PAGE_SIZE = 20;
const ENTITY_TYPES = ["FRAUD_CASE", "CARD", "CREDIT_APPLICATION", "CREDIT_DOCUMENT", "MERCHANT", "CASHBACK_OFFER"];

function actionTagClass(action: string): string {
  if (action === "REJECT" || action === "REJECTED") return "tag tag--warning";
  if (action === "APPROVE" || action === "APPROVED" || action === "ACTIVATE_CARD") return "tag tag--accent";
  return "tag tag--neutral";
}

function formatDiff(oldData: Record<string, unknown> | null, newData: Record<string, unknown> | null): string {
  const parts: string[] = [];
  const keys = new Set([...Object.keys(oldData ?? {}), ...Object.keys(newData ?? {})]);
  for (const key of keys) {
    const before = oldData?.[key];
    const after = newData?.[key];
    if (before !== undefined && after !== undefined) parts.push(`${key}: ${before} → ${after}`);
    else if (after !== undefined) parts.push(`${key}: ${after}`);
    else if (before !== undefined) parts.push(`${key}: ${before}`);
  }
  return parts.join(", ") || "—";
}

export function AuditLogPage() {
  const { t } = useTranslation();
  const { accessToken, logout, user } = useAuth();
  const [logs, setLogs] = useState<AdminAuditLog[]>([]);
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || user?.role !== "ADMIN") {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String((page - 1) * PAGE_SIZE),
    });
    if (entityType) params.set("entity_type", entityType);
    apiRequest<AdminAuditLog[]>(`/audit?${params.toString()}`, { token: accessToken })
      .then((response) => {
        setLogs(response);
        setHasNextPage(response.length === PAGE_SIZE);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setError(err instanceof ApiError ? err.message : t("admin.couldNotLoadAuditLog"));
        setLogs([]);
      })
      .finally(() => setLoading(false));
  }, [accessToken, logout, user?.role, entityType, page, t]);

  if (user?.role !== "ADMIN") {
    return (
      <section className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.auditLog")}</span>
        </div>
        <div className="card-empty">{t("admin.adminPrivilegesRequired")}</div>
      </section>
    );
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.auditLog")}</span>
        </div>
        <p style={{ margin: "0 0 0.85rem", color: "var(--color-text-muted)" }}>{t("admin.auditLogDescription")}</p>
        <label style={{ maxWidth: 260 }}>
          <span className="eyebrow">{t("admin.entityType")}</span>
          <select
            value={entityType}
            onChange={(e) => {
              setEntityType(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{t("admin.allEntityTypes")}</option>
            {ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="tile">
        {error && <p role="alert" style={{ color: "var(--color-warning)" }}>{error}</p>}
        {loading && <div className="card-empty">{t("admin.loadingAuditLog")}</div>}
        {!loading && (
          <>
            <table>
              <thead>
                <tr>
                  <th>{t("admin.when")}</th>
                  <th>{t("admin.adminId")}</th>
                  <th>{t("admin.action")}</th>
                  <th>{t("admin.entity")}</th>
                  <th>{t("admin.change")}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>{new Date(log.created_at).toLocaleString()}</td>
                    <td title={log.admin_user_id}>{log.admin_user_id.slice(0, 8)}</td>
                    <td>
                      <span className={actionTagClass(log.action)}>{log.action}</span>
                    </td>
                    <td>
                      {log.entity_type} <span title={log.entity_id}>({log.entity_id.slice(0, 8)})</span>
                    </td>
                    <td style={{ fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
                      {formatDiff(log.old_data, log.new_data)}
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={5}>{t("admin.noAuditLogEntries")}</td>
                  </tr>
                )}
              </tbody>
            </table>
            {(page > 1 || hasNextPage) && (
              <div
                style={{
                  alignItems: "center",
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: "0.35rem",
                  marginTop: "1rem",
                }}
              >
                <button
                  type="button"
                  className="button--ghost"
                  aria-label={t("admin.previousPage")}
                  disabled={page === 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                  style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
                >
                  <ChevronLeft size={16} aria-hidden="true" />
                </button>
                <span className="eyebrow" style={{ padding: "0 0.4rem" }}>
                  {t("admin.pageNumber", { page })}
                </span>
                <button
                  type="button"
                  className="button--ghost"
                  aria-label={t("admin.nextPage")}
                  disabled={!hasNextPage}
                  onClick={() => setPage((value) => value + 1)}
                  style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
                >
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

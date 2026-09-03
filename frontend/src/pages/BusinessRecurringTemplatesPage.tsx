import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { BulkTransferResult, BulkTransferTemplate } from "../types";

export function BusinessRecurringTemplatesPage() {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const isBusiness = user?.user_type === "BUSINESS";

  const [templates, setTemplates] = useState<BulkTransferTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateActionId, setTemplateActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkTransferResult | null>(null);
  const [expandedTemplateId, setExpandedTemplateId] = useState<string | null>(null);

  async function loadTemplates(token: string) {
    setTemplatesLoading(true);
    try {
      const list = await apiRequest<BulkTransferTemplate[]>("/payments/transfers/bulk/templates", { token });
      setTemplates(list);
    } catch {
      setTemplates([]);
    } finally {
      setTemplatesLoading(false);
    }
  }

  useEffect(() => {
    if (!isBusiness || !accessToken) return;
    void loadTemplates(accessToken);
  }, [isBusiness, accessToken]);

  if (!isBusiness) {
    return (
      <section className="tile">
        <p>{t("businessBulkTransfer.onlyForBusiness")}</p>
      </section>
    );
  }

  async function runTemplate(template: BulkTransferTemplate) {
    if (!accessToken || templateActionId) return;
    setTemplateActionId(template.id);
    setError(null);
    try {
      const response = await apiRequest<BulkTransferResult>(
        `/payments/transfers/bulk/templates/${template.id}/run`,
        { method: "POST", token: accessToken },
      );
      setResult(response);
      void loadTemplates(accessToken);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("businessBulkTransfer.templateRunFailed"));
    } finally {
      setTemplateActionId(null);
    }
  }

  async function updateTemplateStatus(template: BulkTransferTemplate, status: "ACTIVE" | "PAUSED" | "CANCELLED") {
    if (!accessToken || templateActionId) return;
    setTemplateActionId(template.id);
    setError(null);
    try {
      await apiRequest<BulkTransferTemplate>(`/payments/transfers/bulk/templates/${template.id}/status`, {
        method: "PATCH",
        token: accessToken,
        body: { status },
      });
      void loadTemplates(accessToken);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("businessBulkTransfer.templateStatusFailed"));
    } finally {
      setTemplateActionId(null);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("businessBulkTransfer.templatesTitle")}</span>
          {templatesLoading && <span className="tag tag--neutral">{t("businessBulkTransfer.loading")}</span>}
        </div>
        <p style={{ color: "var(--color-text-muted)", marginTop: 0 }}>{t("businessBulkTransfer.templatesSubtitle")}</p>
        <table>
          <thead>
            <tr>
              <th>{t("businessBulkTransfer.templateName")}</th>
              <th>{t("payments.frequency")}</th>
              <th>{t("payments.nextRun")}</th>
              <th>{t("businessBulkTransfer.rows")}</th>
              <th>{t("common.statusLabel")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {templates.map((template) => {
              const isExpanded = expandedTemplateId === template.id;
              return (
                <Fragment key={template.id}>
                  <tr>
                    <td>{template.name}</td>
                    <td>{t(`payments.frequencyOption.${template.frequency}`)}</td>
                    <td>{new Date(`${template.next_run_on}T00:00:00`).toLocaleDateString()}</td>
                    <td>
                      <button
                        type="button"
                        className="button--ghost"
                        onClick={() => setExpandedTemplateId(isExpanded ? null : template.id)}
                      >
                        {t("businessBulkTransfer.rowsCount", { count: template.rows.length })}
                        {isExpanded ? " ▴" : " ▾"}
                      </button>
                    </td>
                    <td>
                      <span className={`tag ${template.status === "ACTIVE" ? "tag--accent" : "tag--neutral"}`}>
                        {t(`payments.scheduledStatusBadge.${template.status.toLowerCase()}`, {
                          defaultValue: template.status,
                        })}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {template.status === "ACTIVE" && (
                          <button
                            type="button"
                            onClick={() => runTemplate(template)}
                            disabled={templateActionId === template.id}
                          >
                            {t("businessBulkTransfer.runNow")}
                          </button>
                        )}
                        {template.status === "ACTIVE" && (
                          <button
                            type="button"
                            className="button--ghost"
                            onClick={() => updateTemplateStatus(template, "PAUSED")}
                            disabled={templateActionId === template.id}
                          >
                            {t("payments.pause")}
                          </button>
                        )}
                        {template.status === "PAUSED" && (
                          <button
                            type="button"
                            className="button--ghost"
                            onClick={() => updateTemplateStatus(template, "ACTIVE")}
                            disabled={templateActionId === template.id}
                          >
                            {t("payments.resume")}
                          </button>
                        )}
                        {template.status !== "CANCELLED" && (
                          <button
                            type="button"
                            className="button--danger"
                            onClick={() => updateTemplateStatus(template, "CANCELLED")}
                            disabled={templateActionId === template.id}
                          >
                            {t("payments.cancel")}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr>
                      <td colSpan={6}>
                        <table>
                          <thead>
                            <tr>
                              <th>{t("businessBulkTransfer.beneficiaryName")}</th>
                              <th>{t("businessBulkTransfer.iban")}</th>
                              <th style={{ textAlign: "right" }}>{t("businessBulkTransfer.amount")}</th>
                              <th>{t("businessBulkTransfer.description")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {template.rows.map((row) => (
                              <tr key={row.id}>
                                <td>{row.beneficiary_name}</td>
                                <td>{row.iban}</td>
                                <td style={{ textAlign: "right" }}>
                                  {row.amount} {template.currency}
                                </td>
                                <td>{row.description ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {!templatesLoading && templates.length === 0 && (
              <tr>
                <td colSpan={6}>{t("businessBulkTransfer.noTemplatesYet")}</td>
              </tr>
            )}
          </tbody>
        </table>
        {error && <p className="status-line status-line--error">{error}</p>}
      </div>

      {result && (
        <div className="tile">
          <div className="tile__header">
            <span className="eyebrow">
              {t("businessBulkTransfer.resultsTitle", { succeeded: result.succeeded, failed: result.failed })}
            </span>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t("businessBulkTransfer.beneficiaryName")}</th>
                <th>{t("businessBulkTransfer.iban")}</th>
                <th style={{ textAlign: "right" }}>{t("businessBulkTransfer.amount")}</th>
                <th>{t("common.statusLabel")}</th>
              </tr>
            </thead>
            <tbody>
              {result.results.map((row, index) => (
                <tr key={`${row.iban}-${index}`}>
                  <td>{row.beneficiary_name}</td>
                  <td>{row.iban}</td>
                  <td style={{ textAlign: "right" }}>{row.amount}</td>
                  <td>
                    {row.error ? (
                      <span className="tag tag--warning" title={row.error}>
                        {t("businessBulkTransfer.failed")}
                      </span>
                    ) : (
                      <span className="tag tag--accent">
                        {t(`common.status.${row.status}`, { defaultValue: row.status ?? "" })}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

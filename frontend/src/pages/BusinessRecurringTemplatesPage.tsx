import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { BulkTransferResult, BulkTransferTemplate, ScheduledPaymentFrequency } from "../types";

const TEMPLATE_FREQUENCIES: ScheduledPaymentFrequency[] = ["ONCE", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"];

interface EditRowDraft {
  beneficiary_name: string;
  iban: string;
  amount: string;
  description: string;
}

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
  const [editingTemplateId, setEditingTemplateId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editFrequency, setEditFrequency] = useState<ScheduledPaymentFrequency>("MONTHLY");
  const [editNextRunOn, setEditNextRunOn] = useState("");
  const [editRows, setEditRows] = useState<EditRowDraft[]>([]);
  const [savingEdit, setSavingEdit] = useState(false);

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

  function startEdit(template: BulkTransferTemplate) {
    setEditingTemplateId(template.id);
    setExpandedTemplateId(template.id);
    setEditName(template.name);
    setEditFrequency(template.frequency);
    setEditNextRunOn(template.next_run_on);
    setEditRows(
      template.rows.map((row) => ({
        beneficiary_name: row.beneficiary_name,
        iban: row.iban,
        amount: row.amount,
        description: row.description ?? "",
      })),
    );
    setError(null);
  }

  function cancelEdit() {
    setEditingTemplateId(null);
  }

  function updateEditRow(index: number, field: keyof EditRowDraft, value: string) {
    setEditRows((current) => current.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }

  function addEditRow() {
    setEditRows((current) => [...current, { beneficiary_name: "", iban: "", amount: "", description: "" }]);
  }

  function removeEditRow(index: number) {
    setEditRows((current) => current.filter((_, i) => i !== index));
  }

  async function saveEdit(templateId: string) {
    if (!accessToken || savingEdit) return;
    const rows = editRows
      .filter((row) => row.beneficiary_name.trim() && row.iban.trim() && row.amount.trim())
      .map((row) => ({
        beneficiary_name: row.beneficiary_name.trim(),
        iban: row.iban.trim(),
        amount: row.amount.trim(),
        description: row.description.trim() || null,
      }));
    if (rows.length === 0) {
      setError(t("businessBulkTransfer.templateNeedsAtLeastOneRow"));
      return;
    }
    setSavingEdit(true);
    setError(null);
    try {
      await apiRequest<BulkTransferTemplate>(`/payments/transfers/bulk/templates/${templateId}`, {
        method: "PUT",
        token: accessToken,
        body: {
          name: editName.trim(),
          frequency: editFrequency,
          next_run_on: editNextRunOn,
          rows,
        },
      });
      setEditingTemplateId(null);
      void loadTemplates(accessToken);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("businessBulkTransfer.templateEditFailed"));
    } finally {
      setSavingEdit(false);
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
                            className="button--ghost"
                            onClick={() => (editingTemplateId === template.id ? cancelEdit() : startEdit(template))}
                          >
                            {editingTemplateId === template.id
                              ? t("businessBulkTransfer.cancelEdit")
                              : t("businessBulkTransfer.editTemplate")}
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
                  {isExpanded && editingTemplateId === template.id && (
                    <tr>
                      <td colSpan={6}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "minmax(0,1.6fr) minmax(0,1fr) minmax(0,1fr)",
                              gap: "0.5rem",
                            }}
                          >
                            <label>
                              {t("businessBulkTransfer.templateName")}
                              <input value={editName} onChange={(e) => setEditName(e.target.value)} />
                            </label>
                            <label>
                              {t("payments.frequency")}
                              <select
                                value={editFrequency}
                                onChange={(e) => setEditFrequency(e.target.value as ScheduledPaymentFrequency)}
                              >
                                {TEMPLATE_FREQUENCIES.map((frequency) => (
                                  <option key={frequency} value={frequency}>
                                    {t(`payments.frequencyOption.${frequency}`)}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("payments.nextRun")}
                              <input
                                type="date"
                                value={editNextRunOn}
                                onChange={(e) => setEditNextRunOn(e.target.value)}
                              />
                            </label>
                          </div>
                          <table>
                            <thead>
                              <tr>
                                <th>{t("businessBulkTransfer.beneficiaryName")}</th>
                                <th>{t("businessBulkTransfer.iban")}</th>
                                <th style={{ textAlign: "right" }}>{t("businessBulkTransfer.amount")}</th>
                                <th>{t("businessBulkTransfer.description")}</th>
                                <th />
                              </tr>
                            </thead>
                            <tbody>
                              {editRows.map((row, index) => (
                                <tr key={index}>
                                  <td>
                                    <input
                                      value={row.beneficiary_name}
                                      onChange={(e) => updateEditRow(index, "beneficiary_name", e.target.value)}
                                    />
                                  </td>
                                  <td>
                                    <input value={row.iban} onChange={(e) => updateEditRow(index, "iban", e.target.value)} />
                                  </td>
                                  <td>
                                    <input
                                      type="number"
                                      min="0.01"
                                      step="0.01"
                                      style={{ textAlign: "right" }}
                                      value={row.amount}
                                      onChange={(e) => updateEditRow(index, "amount", e.target.value)}
                                    />
                                  </td>
                                  <td>
                                    <input
                                      value={row.description}
                                      onChange={(e) => updateEditRow(index, "description", e.target.value)}
                                    />
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      className="button--danger"
                                      onClick={() => removeEditRow(index)}
                                      disabled={editRows.length === 1}
                                    >
                                      {t("businessBulkTransfer.removeRow")}
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button type="button" className="button--ghost" onClick={addEditRow}>
                              {t("businessBulkTransfer.addRow")}
                            </button>
                            <button
                              type="button"
                              onClick={() => saveEdit(template.id)}
                              disabled={savingEdit || !editName.trim() || !editNextRunOn}
                            >
                              {savingEdit ? t("businessBulkTransfer.submitting") : t("businessBulkTransfer.saveTemplate")}
                            </button>
                            <button type="button" className="button--ghost" onClick={cancelEdit}>
                              {t("businessBulkTransfer.cancelEdit")}
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                  {isExpanded && editingTemplateId !== template.id && (
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

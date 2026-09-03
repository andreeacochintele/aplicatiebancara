import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { BulkTransferResult, BulkTransferTemplate, ScheduledPaymentFrequency, Wallet } from "../types";
import { walletLabel } from "../utils";

const TEMPLATE_FREQUENCIES: ScheduledPaymentFrequency[] = ["ONCE", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"];

interface BulkRowForm {
  beneficiary_name: string;
  iban: string;
  amount: string;
  description: string;
}

const EMPTY_ROW: BulkRowForm = { beneficiary_name: "", iban: "", amount: "", description: "" };

/** Splits pasted lines like "Ana Ionescu, RO49AAAA..., 1500, Salariu august"
 * into rows — the fast path for payroll-style lists copied from a
 * spreadsheet. Blank lines are ignored; each line needs at least a name,
 * an IBAN and an amount. */
function parsePastedRows(text: string): BulkRowForm[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const parts = line.split(/[,;\t]/).map((part) => part.trim());
      return {
        beneficiary_name: parts[0] ?? "",
        iban: (parts[1] ?? "").replace(/\s+/g, "").toUpperCase(),
        amount: parts[2] ?? "",
        description: parts[3] ?? "",
      };
    })
    .filter((row) => row.beneficiary_name && row.iban && row.amount);
}

export function BusinessBulkTransferPage() {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const isBusiness = user?.user_type === "BUSINESS";

  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [sourceWalletId, setSourceWalletId] = useState("");
  const [rows, setRows] = useState<BulkRowForm[]>([{ ...EMPTY_ROW }]);
  const [pasteText, setPasteText] = useState("");
  const [saveBeneficiaries, setSaveBeneficiaries] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BulkTransferResult | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [templateNotice, setTemplateNotice] = useState<string | null>(null);
  const [showSaveTemplate, setShowSaveTemplate] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateFrequency, setTemplateFrequency] = useState<ScheduledPaymentFrequency>("MONTHLY");
  const [templateNextRunOn, setTemplateNextRunOn] = useState(() => new Date().toISOString().slice(0, 10));
  const [savingTemplate, setSavingTemplate] = useState(false);

  useEffect(() => {
    if (!isBusiness || !accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken })
      .then((list) => {
        setWallets(list);
        setSourceWalletId((current) => current || list[0]?.id || "");
      })
      .catch(() => setWallets([]));
  }, [isBusiness, accessToken]);

  if (!isBusiness) {
    return (
      <section className="tile">
        <p>{t("businessBulkTransfer.onlyForBusiness")}</p>
      </section>
    );
  }

  const sourceWallet = wallets.find((wallet) => wallet.id === sourceWalletId);
  const validRows = rows.filter((row) => row.beneficiary_name.trim() && row.iban.trim() && Number(row.amount) > 0);
  const totalAmount = validRows.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);

  function updateRow(index: number, field: keyof BulkRowForm, value: string) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }

  function addRow() {
    setRows((current) => [...current, { ...EMPTY_ROW }]);
  }

  function removeRow(index: number) {
    setRows((current) => (current.length > 1 ? current.filter((_, i) => i !== index) : current));
  }

  function applyPaste() {
    const parsed = parsePastedRows(pasteText);
    if (parsed.length === 0) return;
    setRows(parsed);
    setPasteText("");
  }

  async function submit() {
    if (!accessToken || !sourceWallet || validRows.length === 0) return;
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const response = await apiRequest<BulkTransferResult>("/payments/transfers/bulk", {
        method: "POST",
        token: accessToken,
        body: {
          source_wallet_id: sourceWallet.id,
          currency: sourceWallet.currency,
          save_beneficiaries: saveBeneficiaries,
          rows: validRows.map((row) => ({
            beneficiary_name: row.beneficiary_name.trim(),
            iban: row.iban.trim(),
            amount: row.amount,
            description: row.description.trim() || null,
          })),
        },
      });
      setResult(response);
      if (response.failed === 0) {
        setRows([{ ...EMPTY_ROW }]);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("businessBulkTransfer.submitFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveAsTemplate() {
    if (!accessToken || !sourceWallet || validRows.length === 0 || !templateName.trim()) return;
    setTemplateError(null);
    setTemplateNotice(null);
    setSavingTemplate(true);
    try {
      await apiRequest<BulkTransferTemplate>("/payments/transfers/bulk/templates", {
        method: "POST",
        token: accessToken,
        body: {
          name: templateName.trim(),
          source_wallet_id: sourceWallet.id,
          currency: sourceWallet.currency,
          frequency: templateFrequency,
          next_run_on: templateNextRunOn,
          rows: validRows.map((row) => ({
            beneficiary_name: row.beneficiary_name.trim(),
            iban: row.iban.trim(),
            amount: row.amount,
            description: row.description.trim() || null,
          })),
        },
      });
      setTemplateName("");
      setShowSaveTemplate(false);
      setTemplateNotice(t("businessBulkTransfer.templateSaved"));
    } catch (err) {
      setTemplateError(err instanceof ApiError ? err.message : t("businessBulkTransfer.templateSaveFailed"));
    } finally {
      setSavingTemplate(false);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("businessBulkTransfer.title")}</span>
        </div>
        <p style={{ color: "var(--color-text-muted)", marginTop: 0 }}>{t("businessBulkTransfer.subtitle")}</p>

        <label style={{ maxWidth: 360, display: "block", marginBottom: "1rem" }}>
          {t("businessBulkTransfer.sourceWallet")}
          <select value={sourceWalletId} onChange={(event) => setSourceWalletId(event.target.value)}>
            {wallets.map((wallet) => (
              <option key={wallet.id} value={wallet.id}>
                {walletLabel(wallet)}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: "block" }}>
          {t("businessBulkTransfer.pasteLabel")}
          <textarea
            value={pasteText}
            onChange={(event) => setPasteText(event.target.value)}
            placeholder={t("businessBulkTransfer.pastePlaceholder")}
            rows={3}
            style={{ width: "100%", resize: "vertical" }}
          />
        </label>
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
          <button type="button" className="button--ghost" onClick={applyPaste} disabled={pasteText.trim().length === 0}>
            {t("businessBulkTransfer.applyPaste")}
          </button>
        </div>
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">
            {t("businessBulkTransfer.rowsCount", { count: rows.length })}
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {rows.map((row, index) => (
            <div
              key={index}
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0,1.4fr) minmax(0,1.8fr) minmax(0,0.9fr) minmax(0,1.2fr) auto",
                gap: "0.5rem",
                alignItems: "center",
              }}
            >
              <input
                value={row.beneficiary_name}
                onChange={(event) => updateRow(index, "beneficiary_name", event.target.value)}
                placeholder={t("businessBulkTransfer.beneficiaryName")}
              />
              <input
                value={row.iban}
                onChange={(event) => updateRow(index, "iban", event.target.value)}
                placeholder={t("businessBulkTransfer.iban")}
              />
              <input
                value={row.amount}
                onChange={(event) => updateRow(index, "amount", event.target.value)}
                placeholder={t("businessBulkTransfer.amount")}
                inputMode="decimal"
                type="number"
                min="0.01"
                step="0.01"
              />
              <input
                value={row.description}
                onChange={(event) => updateRow(index, "description", event.target.value)}
                placeholder={t("businessBulkTransfer.description")}
              />
              <button
                type="button"
                className="button--danger"
                onClick={() => removeRow(index)}
                disabled={rows.length === 1}
                aria-label={t("businessBulkTransfer.removeRow")}
              >
                {t("businessBulkTransfer.removeRow")}
              </button>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
          <button type="button" className="button--ghost" onClick={addRow}>
            {t("businessBulkTransfer.addRow")}
          </button>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.75rem" }}>
          <input
            type="checkbox"
            checked={saveBeneficiaries}
            onChange={(event) => setSaveBeneficiaries(event.target.checked)}
          />
          {t("businessBulkTransfer.saveBeneficiaries")}
        </label>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: "1rem",
            flexWrap: "wrap",
            gap: "0.5rem",
          }}
        >
          <span className="eyebrow">
            {t("businessBulkTransfer.totalAmount", {
              amount: totalAmount.toFixed(2),
              currency: sourceWallet?.currency ?? "",
            })}
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className="button--ghost"
              onClick={() => setShowSaveTemplate((current) => !current)}
              disabled={validRows.length === 0 || !sourceWallet}
            >
              {t("businessBulkTransfer.saveAsTemplate")}
            </button>
            <button type="button" onClick={submit} disabled={submitting || validRows.length === 0 || !sourceWallet}>
              {submitting ? t("businessBulkTransfer.submitting") : t("businessBulkTransfer.submit")}
            </button>
          </div>
        </div>

        {showSaveTemplate && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0,1.6fr) minmax(0,1fr) minmax(0,1fr) auto",
              gap: "0.5rem",
              alignItems: "end",
              marginTop: "0.75rem",
              paddingTop: "0.75rem",
              borderTop: "1px solid var(--color-divider)",
            }}
          >
            <label>
              {t("businessBulkTransfer.templateName")}
              <input
                value={templateName}
                onChange={(event) => setTemplateName(event.target.value)}
                placeholder={t("businessBulkTransfer.templateNamePlaceholder")}
              />
            </label>
            <label>
              {t("payments.frequency")}
              <select
                value={templateFrequency}
                onChange={(event) => setTemplateFrequency(event.target.value as ScheduledPaymentFrequency)}
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
                min={new Date().toISOString().slice(0, 10)}
                value={templateNextRunOn}
                onChange={(event) => setTemplateNextRunOn(event.target.value)}
              />
            </label>
            <button type="button" onClick={saveAsTemplate} disabled={savingTemplate || !templateName.trim()}>
              {savingTemplate ? t("businessBulkTransfer.submitting") : t("businessBulkTransfer.saveTemplate")}
            </button>
          </div>
        )}

        {error && <p className="status-line status-line--error">{error}</p>}
        {templateError && <p className="status-line status-line--error">{templateError}</p>}
        {templateNotice && <p className="status-line">{templateNotice}</p>}
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

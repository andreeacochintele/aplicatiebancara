import { Fragment, useEffect, useState } from "react";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type { FraudCaseDetail, FraudCaseSummary } from "../../types";

function formatMoney(value: string, currency: string): string {
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatFlagCode(code: string): string {
  return code
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

export function FraudReviewSection() {
  const { accessToken, logout, user } = useAuth();
  const [cases, setCases] = useState<FraudCaseSummary[]>([]);
  const [details, setDetails] = useState<Record<string, FraudCaseDetail>>({});
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [decisionCaseId, setDecisionCaseId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadCases(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiRequest<FraudCaseSummary[]>("/fraud/cases", { token });
      setCases(response);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not load fraud cases.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken || user?.role !== "ADMIN") {
      setIsLoading(false);
      return;
    }
    void loadCases(accessToken);
  }, [accessToken, logout, user?.role]);

  async function toggleExpand(caseId: string) {
    if (expandedCaseId === caseId) {
      setExpandedCaseId(null);
      return;
    }
    setExpandedCaseId(caseId);
    if (!accessToken || details[caseId]) return;
    try {
      const detail = await apiRequest<FraudCaseDetail>(`/fraud/cases/${caseId}`, { token: accessToken });
      setDetails((current) => ({ ...current, [caseId]: detail }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not load fraud case details.");
    }
  }

  async function decide(caseId: string, action: "APPROVE" | "REJECT") {
    if (!accessToken || decisionCaseId) return;
    setDecisionCaseId(caseId);
    setError(null);
    try {
      await apiRequest<FraudCaseDetail>(`/fraud/cases/${caseId}/decision`, {
        method: "POST",
        token: accessToken,
        body: { action },
      });
      setCases((current) => current.filter((item) => item.id !== caseId));
      setDetails((current) => {
        const next = { ...current };
        delete next[caseId];
        return next;
      });
      if (expandedCaseId === caseId) setExpandedCaseId(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not record the fraud decision.");
    } finally {
      setDecisionCaseId(null);
    }
  }

  if (user?.role !== "ADMIN") {
    return null;
  }

  return (
    <div className="tile">
      <div className="tile__header">
        <span className="eyebrow">Fraud review</span>
        <span className="tag tag--neutral">{cases.length} pending</span>
      </div>
      {error && <p style={{ color: "var(--color-warning)", margin: "0 0 0.85rem" }}>{error}</p>}
      {isLoading && <div className="card-empty">Loading fraud cases...</div>}
      {!isLoading && (
        <table>
          <thead>
            <tr>
              <th>Transaction</th>
              <th>Amount held</th>
              <th>Risk score</th>
              <th>Flags</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((fraudCase) => {
              const detail = details[fraudCase.id];
              const isExpanded = expandedCaseId === fraudCase.id;
              return (
                <Fragment key={fraudCase.id}>
                  <tr>
                    <td>{fraudCase.transaction_id.slice(0, 8)}</td>
                    <td>{formatMoney(fraudCase.hold_amount, detail?.transaction_currency ?? "RON")}</td>
                    <td>{fraudCase.risk_score}</td>
                    <td>
                      <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                        {fraudCase.flag_codes.map((code) => (
                          <span key={code} className="tag tag--outline">
                            {formatFlagCode(code)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>{new Date(fraudCase.created_at).toLocaleString()}</td>
                    <td>
                      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                        <button type="button" className="button--ghost" onClick={() => toggleExpand(fraudCase.id)}>
                          {isExpanded ? "Hide" : "Details"}
                        </button>
                        <button
                          type="button"
                          onClick={() => decide(fraudCase.id, "APPROVE")}
                          disabled={decisionCaseId === fraudCase.id}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="button--ghost"
                          onClick={() => decide(fraudCase.id, "REJECT")}
                          disabled={decisionCaseId === fraudCase.id}
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr>
                      <td colSpan={6}>
                        {!detail && <div className="card-empty">Loading details...</div>}
                        {detail && (
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                            <span>
                              {formatMoney(detail.transaction_amount, detail.transaction_currency)}
                              {detail.transaction_description ? ` — ${detail.transaction_description}` : ""}
                            </span>
                            <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
                              {detail.flags.map((flag) => (
                                <li key={flag.id}>
                                  <strong>{formatFlagCode(flag.code)}</strong> (+{flag.points}): {flag.description}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {cases.length === 0 && (
              <tr>
                <td colSpan={6}>No fraud cases pending review.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}

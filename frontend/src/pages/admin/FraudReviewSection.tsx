import { Fragment, useEffect, useState } from "react";
import { Bot, Loader2 } from "lucide-react";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type { FraudAgentAnalysis, FraudCaseDetail, FraudCaseSummary, FraudFlag, FraudFlagCode } from "../../types";

function formatMoney(value: string, currency: string): string {
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatFlagCode(code: string): string {
  return code
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function amountBaseline(analysis: FraudAgentAnalysis | null): Record<string, unknown> {
  return asRecord(asRecord(analysis?.behavioral_analysis).amount_baseline);
}

function velocityWindow(analysis: FraudAgentAnalysis | null, window: string): Record<string, unknown> {
  return asRecord(asRecord(asRecord(analysis?.velocity_analysis).windows)[window]);
}

function reviewFocus(flags: FraudFlag[]): string[] {
  const messages: Record<FraudFlagCode, string> = {
    NEW_DEVICE: "Confirm whether the active device belongs to the customer and whether it has successful prior usage.",
    HIGH_AMOUNT: "Compare the held amount with the customer's completed card-payment baseline and recent large purchases.",
    UNUSUAL_COUNTRY: "Check whether the device location matches the customer's known locations before relying on it.",
    REWARD_ABUSE_PATTERN: "Review same-amount payments to this merchant and separate duplicate checkout attempts from coordinated abuse.",
    HIGH_VELOCITY: "Inspect transactions immediately before and after this payment to understand the burst pattern.",
    UNUSUAL_TIME: "Check whether this UTC transaction time is unusual for this customer, not just unusual in general.",
  };
  return flags.map((flag) => messages[flag.code]);
}

function SignalList({
  items,
  empty,
  tone,
}: {
  items: string[];
  empty: string;
  tone: "risk" | "good" | "gap" | "check";
}) {
  if (items.length === 0) {
    return <p className="fraud-analysis-empty">{empty}</p>;
  }
  return (
    <ul className={`fraud-signal-list fraud-signal-list--${tone}`}>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function FraudReviewSection() {
  const { accessToken, logout, user } = useAuth();
  const [cases, setCases] = useState<FraudCaseSummary[]>([]);
  const [details, setDetails] = useState<Record<string, FraudCaseDetail>>({});
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [decisionCaseId, setDecisionCaseId] = useState<string | null>(null);
  const [investigationCaseId, setInvestigationCaseId] = useState<string | null>(null);
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

  async function investigate(caseId: string) {
    if (!accessToken || investigationCaseId) return;
    setInvestigationCaseId(caseId);
    setError(null);
    try {
      const detail = await apiRequest<FraudCaseDetail>(`/fraud/cases/${caseId}/investigate`, {
        method: "POST",
        token: accessToken,
      });
      setDetails((current) => ({ ...current, [caseId]: detail }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not run the fraud review.");
    } finally {
      setInvestigationCaseId(null);
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
                          <FraudCaseEvidence
                            detail={detail}
                            isInvestigating={investigationCaseId === fraudCase.id}
                            onInvestigate={() => investigate(fraudCase.id)}
                          />
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

function FraudCaseEvidence({
  detail,
  isInvestigating,
  onInvestigate,
}: {
  detail: FraudCaseDetail;
  isInvestigating: boolean;
  onInvestigate: () => void;
}) {
  const analysis = detail.agent_analysis;
  const baseline = amountBaseline(analysis);
  const velocity5m = velocityWindow(analysis, "5m");
  const velocity10m = velocityWindow(analysis, "10m");
  const merchant = asRecord(asRecord(analysis?.merchant_analysis).merchant);
  const device = asRecord(asRecord(analysis?.device_analysis).latest_active_device);
  const historical = asRecord(analysis?.historical_context);
  const hasAnalysis = analysis !== null;

  return (
    <div className="fraud-detail-panel">
      <div className="fraud-detail-panel__top">
        <div>
          <strong>
            {formatMoney(detail.transaction_amount, detail.transaction_currency)}
            {detail.transaction_description ? ` - ${detail.transaction_description}` : ""}
          </strong>
          <span>{new Date(detail.transaction_created_at).toLocaleString()}</span>
        </div>
        <button type="button" className="button--ghost fraud-review-button" onClick={onInvestigate} disabled={isInvestigating}>
          {isInvestigating ? <Loader2 size={14} /> : <Bot size={14} />}
          {hasAnalysis ? "Refresh Review" : "Run Review"}
        </button>
      </div>

      <div className="fraud-analysis-grid">
        <section className="fraud-analysis-block">
          <h4>Triggered Rules</h4>
          <ul className="fraud-rule-list">
            {detail.flags.map((flag) => (
              <li key={flag.id}>
                <strong>{formatFlagCode(flag.code)}</strong>
                <span>+{flag.points}</span>
                <p>{flag.description}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="fraud-analysis-block">
          <h4>Review Focus</h4>
          <SignalList items={reviewFocus(detail.flags)} empty="No rule-specific checks available." tone="check" />
        </section>
      </div>

      {analysis && (
        <>
          <div className="fraud-agent-summary">
            <div>
              <span className="eyebrow">Agent review</span>
              <strong>{analysis.summary ?? analysis.risk_level}</strong>
              <p>{analysis.explanation}</p>
            </div>
            <span className={`tag ${analysis.risk_level === "HIGH" ? "tag--warning" : "tag--neutral"}`}>
              {analysis.risk_level}
            </span>
          </div>

          <div className="fraud-metric-grid">
            <div>
              <span>Average card payment</span>
              <strong>
                {formatValue(baseline.average_completed_card_payment)} {detail.transaction_currency}
              </strong>
            </div>
            <div>
              <span>Amount vs average</span>
              <strong>{formatValue(baseline.amount_to_average_ratio)}x</strong>
            </div>
            <div>
              <span>5 min activity</span>
              <strong>
                {formatValue(velocity5m.count)} tx / {formatValue(velocity5m.total_amount)} {detail.transaction_currency}
              </strong>
            </div>
            <div>
              <span>10 min same merchant</span>
              <strong>{formatValue(velocity10m.same_merchant_count)} tx</strong>
            </div>
            <div>
              <span>Merchant</span>
              <strong>{formatValue(merchant.name ?? "Unknown")}</strong>
            </div>
            <div>
              <span>Latest device</span>
              <strong>{formatValue(device.device_name ?? device.device_type ?? "Unknown")}</strong>
            </div>
            <div>
              <span>Device trusted</span>
              <strong>{device.trusted === true ? "Yes" : device.trusted === false ? "No" : "N/A"}</strong>
            </div>
            <div>
              <span>Previous cases</span>
              <strong>{formatValue(historical.previous_case_count)}</strong>
            </div>
          </div>

          <div className="fraud-analysis-grid">
            <section className="fraud-analysis-block">
              <h4>Suspicious Evidence</h4>
              <SignalList items={analysis.suspicious_signals} empty="No suspicious evidence beyond the triggered rules." tone="risk" />
            </section>
            <section className="fraud-analysis-block">
              <h4>Reassuring Evidence</h4>
              <SignalList items={analysis.reassuring_signals} empty="No reassuring evidence found in available data." tone="good" />
            </section>
            <section className="fraud-analysis-block">
              <h4>Data Gaps</h4>
              <SignalList items={analysis.data_gaps} empty="No notable data gaps." tone="gap" />
            </section>
            <section className="fraud-analysis-block">
              <h4>Manual Checks</h4>
              <SignalList items={analysis.recommended_checks} empty="No additional checks generated." tone="check" />
            </section>
          </div>
        </>
      )}
    </div>
  );
}

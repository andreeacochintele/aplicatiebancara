import { Fragment, useEffect, useState } from "react";
import { Bot, Loader2, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type { FraudAgentAnalysis, FraudCaseDetail, FraudCaseSummary, FraudFlag } from "../../types";
import { formatDecimalAmount } from "../../utils";

function formatMoney(value: string, currency: string): string {
  return `${formatDecimalAmount(Number(value))} ${currency}`;
}

function formatFlagCode(code: string): string {
  return code
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatValue(value: unknown, t: (key: string) => string): string {
  if (value === null || value === undefined || value === "") return t("admin.notAvailable");
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

function reviewFocus(flags: FraudFlag[], t: (key: string) => string): string[] {
  return flags.map((flag) => t(`admin.reviewFocus.${flag.code}`));
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
  const { t } = useTranslation();
  const { accessToken, logout, user } = useAuth();
  const [cases, setCases] = useState<FraudCaseSummary[]>([]);
  const [details, setDetails] = useState<Record<string, FraudCaseDetail>>({});
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [decisionCaseId, setDecisionCaseId] = useState<string | null>(null);
  const [batchDecisionReference, setBatchDecisionReference] = useState<string | null>(null);
  const [investigationCaseId, setInvestigationCaseId] = useState<string | null>(null);
  const [activationCaseId, setActivationCaseId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historyCases, setHistoryCases] = useState<FraudCaseSummary[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  async function loadHistory(token: string) {
    setHistoryLoading(true);
    try {
      const response = await apiRequest<FraudCaseSummary[]>("/fraud/cases/history", { token });
      setHistoryCases(response);
      setHistoryLoaded(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotLoadFraudCases"));
    } finally {
      setHistoryLoading(false);
    }
  }

  function toggleHistory() {
    const next = !showHistory;
    setShowHistory(next);
    if (next && !historyLoaded && accessToken) void loadHistory(accessToken);
  }

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
      setError(err instanceof ApiError ? err.message : t("admin.couldNotLoadFraudCases"));
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
      setError(err instanceof ApiError ? err.message : t("admin.couldNotLoadFraudCaseDetails"));
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
      setError(err instanceof ApiError ? err.message : t("admin.couldNotRecordDecision"));
    } finally {
      setDecisionCaseId(null);
    }
  }

  async function decideBatch(batchReference: string, action: "APPROVE" | "REJECT") {
    if (!accessToken || batchDecisionReference) return;
    const caseIds = cases.filter((item) => item.batch_reference === batchReference).map((item) => item.id);
    if (caseIds.length === 0) return;
    setBatchDecisionReference(batchReference);
    setError(null);
    try {
      for (const caseId of caseIds) {
        await apiRequest<FraudCaseDetail>(`/fraud/cases/${caseId}/decision`, {
          method: "POST",
          token: accessToken,
          body: { action },
        });
      }
      setCases((current) => current.filter((item) => item.batch_reference !== batchReference));
      setDetails((current) => {
        const next = { ...current };
        for (const caseId of caseIds) delete next[caseId];
        return next;
      });
      if (expandedCaseId && caseIds.includes(expandedCaseId)) setExpandedCaseId(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotRecordDecision"));
    } finally {
      setBatchDecisionReference(null);
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
      setError(err instanceof ApiError ? err.message : t("admin.couldNotRunReview"));
    } finally {
      setInvestigationCaseId(null);
    }
  }

  async function activateCard(caseId: string) {
    if (!accessToken || activationCaseId) return;
    setActivationCaseId(caseId);
    setError(null);
    try {
      const detail = await apiRequest<FraudCaseDetail>(`/fraud/cases/${caseId}/activate-card`, {
        method: "POST",
        token: accessToken,
      });
      setDetails((current) => ({ ...current, [caseId]: detail }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotActivateCard"));
    } finally {
      setActivationCaseId(null);
    }
  }

  if (user?.role !== "ADMIN") {
    return null;
  }

  return (
    <>
    <div className="tile">
      <div className="tile__header">
        <span className="eyebrow">{t("admin.fraudReviewTitle")}</span>
        <span className="tag tag--neutral">{t("admin.pendingCount", { count: cases.length })}</span>
      </div>
      {error && <p style={{ color: "var(--color-warning)", margin: "0 0 0.85rem" }}>{error}</p>}
      {isLoading && <div className="card-empty">{t("admin.loadingFraudCases")}</div>}
      {!isLoading && (
        <table>
          <thead>
            <tr>
              <th>{t("admin.transaction")}</th>
              <th>{t("admin.amountHeld")}</th>
              <th>{t("admin.riskScore")}</th>
              <th>{t("admin.flags")}</th>
              <th>{t("admin.created")}</th>
              <th>{t("admin.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {(() => {
              const renderedBatches = new Set<string>();
              return cases.map((fraudCase) => {
                if (fraudCase.batch_reference) {
                  if (renderedBatches.has(fraudCase.batch_reference)) return null;
                  renderedBatches.add(fraudCase.batch_reference);
                  const group = cases.filter((item) => item.batch_reference === fraudCase.batch_reference);
                  return (
                    <BatchGroup
                      key={fraudCase.batch_reference}
                      batchReference={fraudCase.batch_reference}
                      group={group}
                      details={details}
                      expandedCaseId={expandedCaseId}
                      onToggleExpand={toggleExpand}
                      onDecide={decide}
                      decisionCaseId={decisionCaseId}
                      onDecideBatch={decideBatch}
                      isDecidingBatch={batchDecisionReference === fraudCase.batch_reference}
                      investigationCaseId={investigationCaseId}
                      onInvestigate={investigate}
                      activationCaseId={activationCaseId}
                      onActivateCard={activateCard}
                    />
                  );
                }
                return (
                  <CaseRow
                    key={fraudCase.id}
                    fraudCase={fraudCase}
                    detail={details[fraudCase.id]}
                    isExpanded={expandedCaseId === fraudCase.id}
                    onToggleExpand={() => toggleExpand(fraudCase.id)}
                    onApprove={() => decide(fraudCase.id, "APPROVE")}
                    onReject={() => decide(fraudCase.id, "REJECT")}
                    isDeciding={decisionCaseId === fraudCase.id}
                    isInvestigating={investigationCaseId === fraudCase.id}
                    onInvestigate={() => investigate(fraudCase.id)}
                    isActivatingCard={activationCaseId === fraudCase.id}
                    onActivateCard={() => activateCard(fraudCase.id)}
                  />
                );
              });
            })()}
            {cases.length === 0 && (
              <tr>
                <td colSpan={6}>{t("admin.noFraudCasesPending")}</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>

    <div className="tile" style={{ marginTop: "1.25rem" }}>
      <div className="tile__header">
        <span className="eyebrow">{t("admin.fraudHistoryTitle")}</span>
        <button type="button" className="button--ghost" onClick={toggleHistory}>
          {showHistory ? t("admin.hide") : t("admin.showHistory")}
        </button>
      </div>
      {showHistory && (
        <>
          {historyLoading && <div className="card-empty">{t("admin.loadingFraudCases")}</div>}
          {!historyLoading && (
            <table>
              <thead>
                <tr>
                  <th>{t("admin.transaction")}</th>
                  <th>{t("admin.amountHeld")}</th>
                  <th>{t("admin.riskScore")}</th>
                  <th>{t("common.statusLabel")}</th>
                  <th>{t("admin.decidedAt")}</th>
                </tr>
              </thead>
              <tbody>
                {historyCases.map((fraudCase) => (
                  <tr key={fraudCase.id}>
                    <td>{fraudCase.transaction_id.slice(0, 8)}</td>
                    <td>{formatMoney(fraudCase.hold_amount, fraudCase.hold_currency)}</td>
                    <td>{fraudCase.risk_score}</td>
                    <td>
                      <span className={fraudCase.status === "APPROVED" ? "tag tag--accent" : "tag tag--warning"}>
                        {t(`common.status.${fraudCase.status}`, { defaultValue: fraudCase.status })}
                      </span>
                    </td>
                    <td>{fraudCase.decided_at ? new Date(fraudCase.decided_at).toLocaleString() : t("admin.notAvailable")}</td>
                  </tr>
                ))}
                {historyCases.length === 0 && (
                  <tr>
                    <td colSpan={5}>{t("admin.noFraudHistoryYet")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
    </>
  );
}

function CaseRow({
  fraudCase,
  detail,
  isExpanded,
  onToggleExpand,
  onApprove,
  onReject,
  isDeciding,
  isInvestigating,
  onInvestigate,
  isActivatingCard,
  onActivateCard,
}: {
  fraudCase: FraudCaseSummary;
  detail: FraudCaseDetail | undefined;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onApprove: () => void;
  onReject: () => void;
  isDeciding: boolean;
  isInvestigating: boolean;
  onInvestigate: () => void;
  isActivatingCard: boolean;
  onActivateCard: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Fragment>
      <tr>
        <td>{fraudCase.transaction_id.slice(0, 8)}</td>
        <td>{formatMoney(fraudCase.hold_amount, fraudCase.hold_currency)}</td>
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
            <button type="button" className="button--ghost" onClick={onToggleExpand}>
              {isExpanded ? t("admin.hide") : t("admin.details")}
            </button>
            <button type="button" onClick={onApprove} disabled={isDeciding}>
              {t("admin.approve")}
            </button>
            <button type="button" className="button--ghost" onClick={onReject} disabled={isDeciding}>
              {t("admin.reject")}
            </button>
          </div>
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={6}>
            {!detail && <div className="card-empty">{t("admin.loadingDetails")}</div>}
            {detail && (
              <FraudCaseEvidence
                detail={detail}
                isInvestigating={isInvestigating}
                onInvestigate={onInvestigate}
                isActivatingCard={isActivatingCard}
                onActivateCard={onActivateCard}
              />
            )}
          </td>
        </tr>
      )}
    </Fragment>
  );
}

function BatchGroup({
  batchReference,
  group,
  details,
  expandedCaseId,
  onToggleExpand,
  onDecide,
  decisionCaseId,
  onDecideBatch,
  isDecidingBatch,
  investigationCaseId,
  onInvestigate,
  activationCaseId,
  onActivateCard,
}: {
  batchReference: string;
  group: FraudCaseSummary[];
  details: Record<string, FraudCaseDetail>;
  expandedCaseId: string | null;
  onToggleExpand: (caseId: string) => void;
  onDecide: (caseId: string, action: "APPROVE" | "REJECT") => void;
  decisionCaseId: string | null;
  onDecideBatch: (batchReference: string, action: "APPROVE" | "REJECT") => void;
  isDecidingBatch: boolean;
  investigationCaseId: string | null;
  onInvestigate: (caseId: string) => void;
  activationCaseId: string | null;
  onActivateCard: (caseId: string) => void;
}) {
  const { t } = useTranslation();
  const totalsByCurrency = new Map<string, number>();
  for (const item of group) {
    totalsByCurrency.set(
      item.hold_currency,
      (totalsByCurrency.get(item.hold_currency) ?? 0) + Number(item.hold_amount),
    );
  }

  return (
    <Fragment>
      <tr className="fraud-batch-header-row">
        <td colSpan={3}>
          <span className="eyebrow">{t("admin.batchOfCases", { count: group.length })}</span>
        </td>
        <td>
          {Array.from(totalsByCurrency.entries())
            .map(([currency, total]) => formatMoney(total.toFixed(2), currency))
            .join(" · ")}
        </td>
        <td />
        <td>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button type="button" onClick={() => onDecideBatch(batchReference, "APPROVE")} disabled={isDecidingBatch}>
              {t("admin.approveBatch")}
            </button>
            <button
              type="button"
              className="button--ghost"
              onClick={() => onDecideBatch(batchReference, "REJECT")}
              disabled={isDecidingBatch}
            >
              {t("admin.rejectBatch")}
            </button>
          </div>
        </td>
      </tr>
      {group.map((fraudCase) => (
        <CaseRow
          key={fraudCase.id}
          fraudCase={fraudCase}
          detail={details[fraudCase.id]}
          isExpanded={expandedCaseId === fraudCase.id}
          onToggleExpand={() => onToggleExpand(fraudCase.id)}
          onApprove={() => onDecide(fraudCase.id, "APPROVE")}
          onReject={() => onDecide(fraudCase.id, "REJECT")}
          isDeciding={decisionCaseId === fraudCase.id || isDecidingBatch}
          isInvestigating={investigationCaseId === fraudCase.id}
          onInvestigate={() => onInvestigate(fraudCase.id)}
          isActivatingCard={activationCaseId === fraudCase.id}
          onActivateCard={() => onActivateCard(fraudCase.id)}
        />
      ))}
    </Fragment>
  );
}

function FraudCaseEvidence({
  detail,
  isInvestigating,
  onInvestigate,
  isActivatingCard,
  onActivateCard,
}: {
  detail: FraudCaseDetail;
  isInvestigating: boolean;
  onInvestigate: () => void;
  isActivatingCard: boolean;
  onActivateCard: () => void;
}) {
  const { t } = useTranslation();
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
          {hasAnalysis ? t("admin.refreshReview") : t("admin.runReview")}
        </button>
      </div>

      {detail.frozen_card && (
        <div className="fraud-card-hold">
          <div>
            <span className="eyebrow">{t("admin.cardFrozenForFraud")}</span>
            <strong>{detail.frozen_card.masked_pan}</strong>
            {detail.card_hold_notice && <p>{detail.card_hold_notice}</p>}
          </div>
          <button type="button" className="fraud-review-button" onClick={onActivateCard} disabled={isActivatingCard}>
            {isActivatingCard ? <Loader2 size={14} /> : <ShieldCheck size={14} />}
            {t("admin.activateCard")}
          </button>
        </div>
      )}

      <div className="fraud-analysis-grid">
        <section className="fraud-analysis-block">
          <h4>{t("admin.triggeredRules")}</h4>
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
          <h4>{t("admin.reviewFocusTitle")}</h4>
          <SignalList items={reviewFocus(detail.flags, t)} empty={t("admin.noRuleSpecificChecks")} tone="check" />
        </section>
      </div>

      {analysis && (
        <>
          <div className="fraud-agent-summary">
            <div>
              <span className="eyebrow">{t("admin.agentReview")}</span>
              <strong>{analysis.summary ?? analysis.risk_level}</strong>
              <p>{analysis.explanation}</p>
            </div>
            <span className={`tag ${analysis.risk_level === "HIGH" ? "tag--warning" : "tag--neutral"}`}>
              {analysis.risk_level}
            </span>
          </div>

          <div className="fraud-metric-grid">
            <div>
              <span>{t("admin.averageCardPayment")}</span>
              <strong>
                {formatValue(baseline.average_completed_card_payment, t)} {detail.transaction_currency}
              </strong>
            </div>
            <div>
              <span>{t("admin.amountVsAverage")}</span>
              <strong>{formatValue(baseline.amount_to_average_ratio, t)}x</strong>
            </div>
            <div>
              <span>{t("admin.activity5min")}</span>
              <strong>
                {formatValue(velocity5m.count, t)} {t("admin.txUnit")} / {formatValue(velocity5m.total_amount, t)} {detail.transaction_currency}
              </strong>
            </div>
            <div>
              <span>{t("admin.sameMerchant10min")}</span>
              <strong>{formatValue(velocity10m.same_merchant_count, t)} {t("admin.txUnit")}</strong>
            </div>
            <div>
              <span>{t("admin.merchant")}</span>
              <strong>{formatValue(merchant.name ?? t("admin.unknown"), t)}</strong>
            </div>
            <div>
              <span>{t("admin.latestDevice")}</span>
              <strong>{formatValue(device.device_name ?? device.device_type ?? t("admin.unknown"), t)}</strong>
            </div>
            <div>
              <span>{t("admin.deviceTrusted")}</span>
              <strong>{device.trusted === true ? t("admin.yes") : device.trusted === false ? t("admin.no") : t("admin.notAvailable")}</strong>
            </div>
            <div>
              <span>{t("admin.previousCases")}</span>
              <strong>{formatValue(historical.previous_case_count, t)}</strong>
            </div>
          </div>

          <div className="fraud-analysis-grid">
            <section className="fraud-analysis-block">
              <h4>{t("admin.suspiciousEvidence")}</h4>
              <SignalList items={analysis.suspicious_signals} empty={t("admin.noSuspiciousEvidence")} tone="risk" />
            </section>
            <section className="fraud-analysis-block">
              <h4>{t("admin.reassuringEvidence")}</h4>
              <SignalList items={analysis.reassuring_signals} empty={t("admin.noReassuringEvidence")} tone="good" />
            </section>
            <section className="fraud-analysis-block">
              <h4>{t("admin.dataGaps")}</h4>
              <SignalList items={analysis.data_gaps} empty={t("admin.noDataGaps")} tone="gap" />
            </section>
            <section className="fraud-analysis-block">
              <h4>{t("admin.manualChecks")}</h4>
              <SignalList items={analysis.recommended_checks} empty={t("admin.noAdditionalChecks")} tone="check" />
            </section>
          </div>
        </>
      )}
    </div>
  );
}

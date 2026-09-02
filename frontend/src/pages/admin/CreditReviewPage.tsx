import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type {
  CreditApplication,
  CreditApplicationStatus,
  CreditDocument,
  CreditDocumentContent,
  CreditDocumentStatus,
  LoanProductType,
} from "../../types";

const PRODUCT_RATE_DEFAULTS: Record<LoanProductType, string> = {
  PERSONAL_LOAN: "9.90",
  MORTGAGE: "6.80",
  AUTO_LOAN: "8.40",
  STUDENT_LOAN: "5.90",
  HOME_IMPROVEMENT: "8.20",
  DEBT_CONSOLIDATION: "10.50",
};
const DEFAULT_VISIBLE_APPLICATIONS = 4;

function defaultRate(application: CreditApplication): string {
  if (application.type === "CREDIT_CARD") return "18.00";
  return application.loan_product_type ? PRODUCT_RATE_DEFAULTS[application.loan_product_type] : "9.50";
}

function formatProductType(type: LoanProductType | null, t: (key: string) => string): string {
  if (!type) return t("admin.generalLoan");
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatApplicationProduct(application: CreditApplication, t: (key: string) => string): string {
  if (application.type === "CREDIT_CARD") return t("admin.creditCard");
  return formatProductType(application.loan_product_type, t);
}

function formatMoney(value: string | null, t: (key: string) => string, currency = "RON"): string {
  if (!value) return t("admin.notAvailable");
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function statusClass(status: CreditApplicationStatus): string {
  if (status === "APPROVED") return "tag tag--accent";
  if (status === "REJECTED") return "tag tag--warning";
  return "tag tag--neutral";
}

function scoreBand(score: number, t: (key: string) => string): string {
  if (score >= 800) return t("admin.excellent");
  if (score >= 740) return t("admin.veryGood");
  if (score >= 670) return t("admin.good");
  if (score >= 580) return t("admin.fair");
  return t("admin.risky");
}

function documentStatusClass(status: CreditDocumentStatus): string {
  if (status === "APPROVED") return "tag tag--accent";
  if (status === "REJECTED") return "tag tag--warning";
  if (status === "NEEDS_MORE_INFO") return "tag tag--neutral";
  return "tag tag--outline";
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function normalizeMatchText(value: string): string {
  return value.replace(/[_-]/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
}

function documentProductMatchesApplication(
  document: CreditDocument,
  application: CreditApplication,
  t: (key: string) => string,
): boolean {
  const documentType = normalizeMatchText(document.document_type);
  const product = normalizeMatchText(formatProductType(application.loan_product_type, t));
  return documentType.includes(product) || product.includes(documentType.replace("documentation", "").trim());
}

function openBase64Document(document: CreditDocumentContent, targetWindow: Window | null) {
  const binary = atob(document.content_base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const blob = new Blob([bytes], { type: document.content_type ?? "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  if (targetWindow) {
    targetWindow.location.href = url;
  } else {
    const link = window.document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.click();
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function CreditReviewPage() {
  const { t } = useTranslation();
  const { accessToken, logout, user } = useAuth();
  const [applications, setApplications] = useState<CreditApplication[]>([]);
  const [documents, setDocuments] = useState<CreditDocument[]>([]);
  const [decisionApplicationId, setDecisionApplicationId] = useState<string | null>(null);
  const [reviewingScoreDocumentId, setReviewingScoreDocumentId] = useState<string | null>(null);
  const [scoreReviewDrafts, setScoreReviewDrafts] = useState<Record<string, string>>({});
  const [moreInfoApplicationId, setMoreInfoApplicationId] = useState<string | null>(null);
  const [viewingDocumentId, setViewingDocumentId] = useState<string | null>(null);
  const [clientSearch, setClientSearch] = useState("");
  const [showAllApplications, setShowAllApplications] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const pendingApplications = useMemo(
    () => applications.filter((application) => application.status === "PENDING" || application.status === "DRAFT"),
    [applications],
  );
  const applicationDocuments = useMemo(
    () => applications.flatMap((application) => application.documents ?? []),
    [applications],
  );
  const allDocuments = useMemo(() => {
    const byId = new Map<string, CreditDocument>();
    for (const document of [...applicationDocuments, ...documents]) {
      byId.set(document.id, document);
    }
    return [...byId.values()];
  }, [applicationDocuments, documents]);
  const inferredDocumentApplicationIds = useMemo(
    () => {
      const claimedApplicationIds = new Set<string>();
      return allDocuments.reduce<Record<string, string>>((matches, document) => {
        if (document.application_id || document.purpose !== "LOAN_APPLICATION") return matches;
        const sameUserApplications = applications.filter((application) => application.user_id === document.user_id);
        const uploadTime = new Date(document.uploaded_at).getTime();
        const candidates = sameUserApplications
          .map((application) => {
            const createdTime = new Date(application.created_at).getTime();
            const productMatch = documentProductMatchesApplication(document, application, t);
            const timingPenalty = Number.isFinite(uploadTime) && Number.isFinite(createdTime) ? Math.abs(uploadTime - createdTime) : 0;
            return { application, productMatch, timingPenalty };
          })
          .filter((candidate) => candidate.productMatch || sameUserApplications.length === 1)
          .sort((left, right) => {
            if (left.productMatch !== right.productMatch) return left.productMatch ? -1 : 1;
            return left.timingPenalty - right.timingPenalty;
          });
        const match = candidates.find((candidate) => !claimedApplicationIds.has(candidate.application.id)) ?? candidates[0];
        if (match) {
          matches[document.id] = match.application.id;
          claimedApplicationIds.add(match.application.id);
        }
        return matches;
      }, {});
    },
    [allDocuments, applications],
  );
  const documentsByApplication = useMemo(
    () =>
      allDocuments.reduce<Record<string, CreditDocument[]>>((groups, document) => {
        const applicationId = document.application_id ?? inferredDocumentApplicationIds[document.id];
        if (!applicationId) return groups;
        groups[applicationId] = [...(groups[applicationId] ?? []), document];
        return groups;
      }, {}),
    [allDocuments, inferredDocumentApplicationIds],
  );
  const creditScoreDocuments = useMemo(
    () =>
      allDocuments
        .filter((document) => document.purpose === "CREDIT_SCORE")
        .sort((left, right) => new Date(right.uploaded_at).getTime() - new Date(left.uploaded_at).getTime()),
    [allDocuments],
  );
  const pendingCreditScoreDocuments = useMemo(
    () => creditScoreDocuments.filter((document) => document.status === "UPLOADED" || document.status === "NEEDS_MORE_INFO"),
    [creditScoreDocuments],
  );
  const searchedApplications = useMemo(() => {
    const query = clientSearch.trim().toLowerCase();
    if (!query) return applications;
    return applications.filter((application) => {
      const fields = [
        application.user_id,
        application.user_id.slice(0, 8),
        formatApplicationProduct(application, t),
        application.status,
        application.currency,
        application.requested_amount,
        application.offered_amount ?? "",
      ];
      return fields.some((field) => field.toLowerCase().includes(query));
    });
  }, [applications, clientSearch]);
  const visibleApplications = useMemo(() => {
    if (clientSearch.trim() || showAllApplications) return searchedApplications;
    return searchedApplications.slice(0, DEFAULT_VISIBLE_APPLICATIONS);
  }, [clientSearch, searchedApplications, showAllApplications]);
  const hiddenApplicationCount = Math.max(0, searchedApplications.length - visibleApplications.length);

  async function loadApplications(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiRequest<CreditApplication[]>("/credit/admin/applications", { token });
      let documentResponse: CreditDocument[] = [];
      try {
        documentResponse = await apiRequest<CreditDocument[]>("/credit/admin/documents", { token });
      } catch {
        documentResponse = [];
      }
      setApplications(response);
      setDocuments(documentResponse);
      setScoreReviewDrafts((current) => {
        const next = { ...current };
        for (const document of documentResponse) {
          if (document.purpose === "CREDIT_SCORE" && next[document.id] === undefined && document.evaluation_score !== null) {
            next[document.id] = String(document.evaluation_score);
          }
        }
        return next;
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotLoadApplications"));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken || user?.role !== "ADMIN") {
      setIsLoading(false);
      return;
    }
    void loadApplications(accessToken);
  }, [accessToken, logout, user?.role]);

  async function decideApplication(application: CreditApplication, status: "APPROVED" | "REJECTED") {
    if (!accessToken || decisionApplicationId) return;
    setDecisionApplicationId(application.id);
    setError(null);
    try {
      const updated = await apiRequest<CreditApplication>(`/credit/admin/applications/${application.id}/decision`, {
        method: "PATCH",
        token: accessToken,
        body:
          status === "APPROVED"
            ? { status, offered_amount: application.requested_amount, offered_interest_rate: defaultRate(application) }
            : { status },
      });
      setApplications((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof Error ? err.message : t("admin.couldNotUpdateApplication"));
    } finally {
      setDecisionApplicationId(null);
    }
  }

  async function requestMoreInfo(application: CreditApplication) {
    if (!accessToken || moreInfoApplicationId) return;

    setMoreInfoApplicationId(application.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiRequest<CreditApplication>(`/credit/admin/applications/${application.id}/more-info`, {
        method: "PATCH",
        token: accessToken,
      });
      const updatedDocuments = updated.documents ?? [];
      setDocuments((current) => {
        const byId = new Map(current.map((document) => [document.id, document]));
        for (const document of updatedDocuments) {
          byId.set(document.id, document);
        }
        return [...byId.values()];
      });
      setApplications((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setNotice(t("admin.moreInfoSent"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotRequestMoreInfo"));
    } finally {
      setMoreInfoApplicationId(null);
    }
  }

  async function reviewCreditScoreDocument(document: CreditDocument, status: "APPROVED" | "NEEDS_MORE_INFO") {
    if (!accessToken || reviewingScoreDocumentId) return;
    const draftScore = Number(scoreReviewDrafts[document.id] ?? document.evaluation_score ?? "");
    if (status === "APPROVED" && (!Number.isInteger(draftScore) || draftScore < 300 || draftScore > 850)) {
      setError(t("admin.scoreOutOfRange"));
      return;
    }
    setReviewingScoreDocumentId(document.id);
    setError(null);
    try {
      const updated = await apiRequest<CreditDocument>(`/credit/admin/documents/${document.id}/review`, {
        method: "PATCH",
        token: accessToken,
        body: {
          status,
          evaluation_score: status === "APPROVED" ? draftScore : null,
          review_note:
            status === "APPROVED"
              ? t("admin.scoreSetByAdmin")
              : t("admin.additionalDocsRequired"),
        },
      });
      setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setApplications((current) =>
        current.map((application) => ({
          ...application,
          documents: application.documents?.map((item) => (item.id === updated.id ? updated : item)),
        })),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotReviewScoreDocument"));
    } finally {
      setReviewingScoreDocumentId(null);
    }
  }

  async function viewDocument(document: CreditDocument) {
    if (!accessToken || viewingDocumentId) return;
    setViewingDocumentId(document.id);
    setError(null);
    const targetWindow = window.open("", "_blank");
    if (targetWindow) {
      targetWindow.document.write(`<p style="font-family: system-ui; padding: 24px;">${t("admin.openingDocument")}</p>`);
      targetWindow.document.close();
    }
    try {
      const content = await apiRequest<CreditDocumentContent>(`/credit/admin/documents/${document.id}/content`, {
        token: accessToken,
      });
      openBase64Document(content, targetWindow);
    } catch (err) {
      targetWindow?.close();
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotOpenDocument"));
    } finally {
      setViewingDocumentId(null);
    }
  }

  if (user?.role !== "ADMIN") {
    return (
      <section className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.creditAndLoans")}</span>
        </div>
        <div className="card-empty">{t("admin.adminPrivilegesRequired")}</div>
      </section>
    );
  }

  function renderSubmissionDocuments(application: CreditApplication) {
    const linkedDocuments = documentsByApplication[application.id] ?? [];
    if (linkedDocuments.length === 0) {
      if (application.type === "CREDIT_CARD") {
        return <span className="admin-submission-documents__empty">{t("admin.notRequired")}</span>;
      }
      return (
        <div className="admin-submission-documents__missing">
          <strong>{t("admin.missingDocuments")}</strong>
          <span>{t("admin.askForIncomeProof")}</span>
        </div>
      );
    }

    return (
      <div className="admin-submission-documents">
        {linkedDocuments.map((document) => {
          return (
            <div className="admin-submission-document" key={document.id}>
              <div className="admin-submission-document__top">
                <div>
                  <strong title={document.file_name}>{document.file_name}</strong>
                  <span>
                    {document.document_type} / {formatFileSize(document.file_size)}
                  </span>
                  {document.review_note && <span className="admin-submission-document__note">{document.review_note}</span>}
                </div>
                <span className={documentStatusClass(document.status)}>{t(`admin.documentStatus.${document.status}`)}</span>
              </div>
              <div className="admin-submission-document__actions">
                <button
                  type="button"
                  className="button--ghost admin-submission-document__view"
                  onClick={() => viewDocument(document)}
                  disabled={viewingDocumentId === document.id}
                >
                  {viewingDocumentId === document.id ? t("admin.opening") : t("admin.view")}
                </button>
                {document.evaluation_score !== null && (
                  <span className="admin-submission-document__score">{document.evaluation_score}/100</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  function renderCreditScoreReview() {
    const visibleDocuments = creditScoreDocuments.slice(0, 4);
    return (
      <div className="admin-score-review">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.creditScoreReview")}</span>
          <span className="tag tag--neutral">{t("admin.pendingScores", { count: pendingCreditScoreDocuments.length })}</span>
        </div>
        {visibleDocuments.length === 0 ? (
          <div className="card-empty">{t("admin.noCreditScoreDocsYet")}</div>
        ) : (
          <div className="admin-score-review__grid">
            {visibleDocuments.map((document) => {
              const isPending = document.status === "UPLOADED" || document.status === "NEEDS_MORE_INFO";
              const isBusy = reviewingScoreDocumentId === document.id;
              return (
                <article className="admin-score-review__card" key={document.id}>
                  <div>
                    <span className="eyebrow">{t("admin.client", { id: document.user_id.slice(0, 8) })}</span>
                    <strong title={document.file_name}>{document.file_name}</strong>
                    <small>
                      {document.document_type} / {formatFileSize(document.file_size)}
                    </small>
                  </div>
                  <div className="admin-score-review__meta">
                    <span className={documentStatusClass(document.status)}>{t(`admin.documentStatus.${document.status}`)}</span>
                    <strong>{t("admin.generatedOutOf850", { score: document.evaluation_score ?? t("admin.notAvailable") })}</strong>
                  </div>
                  {isPending && (
                    <label className="admin-score-review__score-input">
                      <span>{t("admin.adminScore")}</span>
                      <input
                        value={scoreReviewDrafts[document.id] ?? String(document.evaluation_score ?? "")}
                        onChange={(event) =>
                          setScoreReviewDrafts((current) => ({
                            ...current,
                            [document.id]: event.target.value,
                          }))
                        }
                        inputMode="numeric"
                        min={300}
                        max={850}
                      />
                    </label>
                  )}
                  {document.review_note && <p>{document.review_note}</p>}
                  <div className="admin-score-review__actions">
                    <button
                      type="button"
                      className="button--ghost"
                      onClick={() => viewDocument(document)}
                      disabled={viewingDocumentId === document.id}
                    >
                      {viewingDocumentId === document.id ? t("admin.opening") : t("admin.viewDocument")}
                    </button>
                    {isPending && (
                      <>
                        <button
                          type="button"
                          onClick={() => reviewCreditScoreDocument(document, "APPROVED")}
                          disabled={isBusy}
                        >
                          {t("admin.approveScore")}
                        </button>
                        <button
                          type="button"
                          className="button--ghost"
                          onClick={() => reviewCreditScoreDocument(document, "NEEDS_MORE_INFO")}
                          disabled={isBusy}
                        >
                          {t("admin.needMoreInfo")}
                        </button>
                      </>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        {renderCreditScoreReview()}
      </div>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.loanSubmissions")}</span>
          <span className="tag tag--neutral">{t("admin.pendingCredit", { count: pendingApplications.length })}</span>
        </div>
        {error && <p style={{ color: "var(--color-warning)", margin: "0 0 0.85rem" }}>{error}</p>}
        {notice && <p className="admin-dashboard-notice">{notice}</p>}
        {isLoading && <div className="card-empty">{t("admin.loadingApplications")}</div>}
        {!isLoading && (
          <>
            <div className="admin-applications-toolbar">
              <label>
                <span className="eyebrow">{t("admin.searchClient")}</span>
                <input
                  value={clientSearch}
                  onChange={(event) => {
                    setClientSearch(event.target.value);
                    setShowAllApplications(false);
                  }}
                  placeholder={t("admin.searchClientPlaceholder")}
                />
              </label>
              <span className="tag tag--outline">
                {t("admin.shownOfTotal", { shown: visibleApplications.length, total: searchedApplications.length })}
              </span>
            </div>
            <div className="admin-applications-scroll">
              <table className="admin-applications-table">
                <thead>
                  <tr>
                    <th>{t("admin.applicant")}</th>
                    <th>{t("admin.product")}</th>
                    <th>{t("admin.requested")}</th>
                    <th>{t("admin.offer")}</th>
                    <th>{t("admin.rate")}</th>
                    <th>{t("admin.creditScore")}</th>
                    <th>{t("admin.status")}</th>
                    <th className="admin-applications-table__documents-heading">{t("admin.documents")}</th>
                    <th>{t("admin.created")}</th>
                    <th>{t("admin.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleApplications.map((application) => {
                    const isOpen = application.status === "PENDING" || application.status === "DRAFT";
                    const offerAmount = application.offered_amount ?? application.requested_amount;
                    const displayRate = application.offered_interest_rate ?? defaultRate(application);
                    const hasMoreInfoRequested = (documentsByApplication[application.id] ?? []).some(
                      (document) => document.status === "NEEDS_MORE_INFO",
                    );
                    const canRequestMoreInfo = application.type === "PERSONAL_LOAN";
                    return (
                      <tr key={application.id}>
                        <td>{application.user_id.slice(0, 8)}</td>
                        <td>{formatApplicationProduct(application, t)}</td>
                        <td>{formatMoney(application.requested_amount, t, application.currency)}</td>
                        <td>{formatMoney(offerAmount, t, application.currency)}</td>
                        <td>{displayRate}</td>
                        <td>
                          <div className="admin-credit-score">
                            <strong>{application.credit_score_at_application}</strong>
                            <span>{scoreBand(application.credit_score_at_application, t)}</span>
                          </div>
                        </td>
                        <td className="admin-applications-table__status-cell">
                          <span className={`${statusClass(application.status)} admin-status-pill`}>{application.status}</span>
                        </td>
                        <td className="admin-applications-table__documents-cell">{renderSubmissionDocuments(application)}</td>
                        <td>{application.created_at ? new Date(application.created_at).toLocaleDateString() : t("admin.notAvailable")}</td>
                        <td>
                          {isOpen ? (
                            <div className="admin-submission-actions">
                              <button
                                type="button"
                                onClick={() => decideApplication(application, "APPROVED")}
                                disabled={decisionApplicationId === application.id}
                              >
                                {t("admin.approve")}
                              </button>
                              {canRequestMoreInfo && (
                                <button
                                  type="button"
                                  className="button--ghost"
                                  onClick={() => requestMoreInfo(application)}
                                  disabled={moreInfoApplicationId === application.id || hasMoreInfoRequested}
                                >
                                  {moreInfoApplicationId === application.id
                                    ? t("admin.requesting")
                                    : hasMoreInfoRequested
                                      ? t("admin.infoRequested")
                                      : t("admin.needMoreInfo")}
                                </button>
                              )}
                              <button
                                type="button"
                                className="button--ghost"
                                onClick={() => decideApplication(application, "REJECTED")}
                                disabled={decisionApplicationId === application.id}
                              >
                                {t("admin.reject")}
                              </button>
                            </div>
                          ) : (
                            <span className="tag tag--neutral">
                              {application.status === "APPROVED" ? t("admin.reviewed") : t(`common.status.${application.status}`, { defaultValue: application.status.replaceAll("_", " ") })}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {searchedApplications.length === 0 && (
                    <tr>
                      <td colSpan={10}>{t("admin.noApplicationsFound")}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {!clientSearch.trim() && hiddenApplicationCount > 0 && (
              <div className="admin-applications-footer">
                <button
                  type="button"
                  className="button--ghost"
                  onClick={() => setShowAllApplications((current) => !current)}
                >
                  {showAllApplications ? t("admin.showLess") : t("admin.showMore", { count: hiddenApplicationCount })}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

import { useEffect, useMemo, useState } from "react";

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
import { FraudReviewSection } from "./FraudReviewSection";

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

function formatProductType(type: LoanProductType | null): string {
  if (!type) return "General loan";
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatMoney(value: string | null, currency = "RON"): string {
  if (!value) return "N/A";
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function statusClass(status: CreditApplicationStatus): string {
  if (status === "APPROVED") return "tag tag--accent";
  if (status === "REJECTED") return "tag tag--warning";
  return "tag tag--neutral";
}

function scoreBand(score: number): string {
  if (score >= 800) return "Excellent";
  if (score >= 740) return "Very good";
  if (score >= 670) return "Good";
  if (score >= 580) return "Fair";
  return "Risky";
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

function documentProductMatchesApplication(document: CreditDocument, application: CreditApplication): boolean {
  const documentType = normalizeMatchText(document.document_type);
  const product = normalizeMatchText(formatProductType(application.loan_product_type));
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

export function AdminDashboardPage() {
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
            const productMatch = documentProductMatchesApplication(document, application);
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
        formatProductType(application.loan_product_type),
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
      setError(err instanceof ApiError ? err.message : "Could not load loan applications.");
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
      setError(err instanceof Error ? err.message : "Could not update loan application.");
    } finally {
      setDecisionApplicationId(null);
    }
  }

  async function requestMoreInfo(application: CreditApplication) {
    if (!accessToken || moreInfoApplicationId) return;
    const pendingDocuments = (documentsByApplication[application.id] ?? []).filter((document) => document.status === "UPLOADED");
    if (pendingDocuments.length === 0) {
      setError("This submission has no pending uploaded documents to request more information on.");
      return;
    }

    setMoreInfoApplicationId(application.id);
    setError(null);
    try {
      const updatedDocuments = await Promise.all(
        pendingDocuments.map((document) =>
          apiRequest<CreditDocument>(`/credit/admin/documents/${document.id}/review`, {
            method: "PATCH",
            token: accessToken,
            body: {
              status: "NEEDS_MORE_INFO",
              evaluation_score: null,
              review_note: "Additional supporting information required.",
            },
          }),
        ),
      );
      setDocuments((current) =>
        current.map((document) => updatedDocuments.find((updated) => updated.id === document.id) ?? document),
      );
      setApplications((current) =>
        current.map((item) =>
          item.id === application.id
            ? {
                ...item,
                documents: item.documents?.map(
                  (document) => updatedDocuments.find((updated) => updated.id === document.id) ?? document,
                ),
              }
            : item,
        ),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not request more information.");
    } finally {
      setMoreInfoApplicationId(null);
    }
  }

  async function reviewCreditScoreDocument(document: CreditDocument, status: "APPROVED" | "NEEDS_MORE_INFO") {
    if (!accessToken || reviewingScoreDocumentId) return;
    const draftScore = Number(scoreReviewDrafts[document.id] ?? document.evaluation_score ?? "");
    if (status === "APPROVED" && (!Number.isInteger(draftScore) || draftScore < 300 || draftScore > 850)) {
      setError("Credit score must be a whole number between 300 and 850.");
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
              ? "Credit score set by admin after document review."
              : "Additional income or debt documentation required.",
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
      setError(err instanceof ApiError ? err.message : "Could not review credit score document.");
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
      targetWindow.document.write("<p style=\"font-family: system-ui; padding: 24px;\">Opening document...</p>");
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
      setError(err instanceof ApiError ? err.message : "Could not open uploaded document.");
    } finally {
      setViewingDocumentId(null);
    }
  }

  if (user?.role !== "ADMIN") {
    return (
      <section className="tile">
        <div className="tile__header">
          <span className="eyebrow">Admin dashboard</span>
        </div>
        <div className="card-empty">Admin privileges required.</div>
      </section>
    );
  }

  function renderSubmissionDocuments(application: CreditApplication) {
    const linkedDocuments = documentsByApplication[application.id] ?? [];
    if (linkedDocuments.length === 0) {
      return (
        <div className="admin-submission-documents__missing">
          <strong>Missing documents</strong>
          <span>Ask client for income/debt proof</span>
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
                </div>
              </div>
              <div className="admin-submission-document__actions">
                <button
                  type="button"
                  className="button--ghost admin-submission-document__view"
                  onClick={() => viewDocument(document)}
                  disabled={viewingDocumentId === document.id}
                >
                  {viewingDocumentId === document.id ? "Opening..." : "View"}
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
          <span className="eyebrow">Credit score review</span>
          <span className="tag tag--neutral">{pendingCreditScoreDocuments.length} pending scores</span>
        </div>
        {visibleDocuments.length === 0 ? (
          <div className="card-empty">No credit score documents uploaded yet.</div>
        ) : (
          <div className="admin-score-review__grid">
            {visibleDocuments.map((document) => {
              const isPending = document.status === "UPLOADED" || document.status === "NEEDS_MORE_INFO";
              const isBusy = reviewingScoreDocumentId === document.id;
              return (
                <article className="admin-score-review__card" key={document.id}>
                  <div>
                    <span className="eyebrow">Client {document.user_id.slice(0, 8)}</span>
                    <strong title={document.file_name}>{document.file_name}</strong>
                    <small>
                      {document.document_type} / {formatFileSize(document.file_size)}
                    </small>
                  </div>
                  <div className="admin-score-review__meta">
                    <span className={documentStatusClass(document.status)}>{document.status.replaceAll("_", " ")}</span>
                    <strong>Generated {document.evaluation_score ?? "N/A"}/850</strong>
                  </div>
                  {isPending && (
                    <label className="admin-score-review__score-input">
                      <span>Admin score</span>
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
                      {viewingDocumentId === document.id ? "Opening..." : "View document"}
                    </button>
                    {isPending && (
                      <>
                        <button
                          type="button"
                          onClick={() => reviewCreditScoreDocument(document, "APPROVED")}
                          disabled={isBusy}
                        >
                          Approve score
                        </button>
                        <button
                          type="button"
                          className="button--ghost"
                          onClick={() => reviewCreditScoreDocument(document, "NEEDS_MORE_INFO")}
                          disabled={isBusy}
                        >
                          Need more info
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
          <span className="eyebrow">Loan submissions</span>
          <span className="tag tag--neutral">{pendingApplications.length} pending credit</span>
        </div>
        {error && <p style={{ color: "var(--color-warning)", margin: "0 0 0.85rem" }}>{error}</p>}
        {isLoading && <div className="card-empty">Loading loan applications...</div>}
        {!isLoading && (
          <>
            <div className="admin-applications-toolbar">
              <label>
                <span className="eyebrow">Search client</span>
                <input
                  value={clientSearch}
                  onChange={(event) => {
                    setClientSearch(event.target.value);
                    setShowAllApplications(false);
                  }}
                  placeholder="Client id, product, status..."
                />
              </label>
              <span className="tag tag--outline">
                {visibleApplications.length} of {searchedApplications.length} shown
              </span>
            </div>
            <div className="admin-applications-scroll">
              <table className="admin-applications-table">
                <thead>
                  <tr>
                    <th>Applicant</th>
                    <th>Product</th>
                    <th>Requested</th>
                    <th>Offer</th>
                    <th>Rate</th>
                    <th>Credit score</th>
                    <th>Status</th>
                    <th className="admin-applications-table__documents-heading">Documents</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleApplications.map((application) => {
                    const isOpen = application.status === "PENDING" || application.status === "DRAFT";
                    const offerAmount = application.offered_amount ?? application.requested_amount;
                    const displayRate = application.offered_interest_rate ?? defaultRate(application);
                    return (
                      <tr key={application.id}>
                        <td>{application.user_id.slice(0, 8)}</td>
                        <td>{formatProductType(application.loan_product_type)}</td>
                        <td>{formatMoney(application.requested_amount, application.currency)}</td>
                        <td>{formatMoney(offerAmount, application.currency)}</td>
                        <td>{displayRate}</td>
                        <td>
                          <div className="admin-credit-score">
                            <strong>{application.credit_score_at_application}</strong>
                            <span>{scoreBand(application.credit_score_at_application)}</span>
                          </div>
                        </td>
                        <td className="admin-applications-table__status-cell">
                          <span className={`${statusClass(application.status)} admin-status-pill`}>{application.status}</span>
                        </td>
                        <td className="admin-applications-table__documents-cell">{renderSubmissionDocuments(application)}</td>
                        <td>{application.created_at ? new Date(application.created_at).toLocaleDateString() : "N/A"}</td>
                        <td>
                          {isOpen ? (
                            <div className="admin-submission-actions">
                              <button
                                type="button"
                                onClick={() => decideApplication(application, "APPROVED")}
                                disabled={decisionApplicationId === application.id}
                              >
                                Approve
                              </button>
                              <button
                                type="button"
                                className="button--ghost"
                                onClick={() => requestMoreInfo(application)}
                                disabled={moreInfoApplicationId === application.id}
                              >
                                Need more info
                              </button>
                              <button
                                type="button"
                                className="button--ghost"
                                onClick={() => decideApplication(application, "REJECTED")}
                                disabled={decisionApplicationId === application.id}
                              >
                                Reject
                              </button>
                            </div>
                          ) : (
                            <span className="tag tag--neutral">
                              {application.status === "APPROVED" ? "Reviewed" : application.status.replaceAll("_", " ")}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {searchedApplications.length === 0 && (
                    <tr>
                      <td colSpan={10}>No loan applications found.</td>
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
                  {showAllApplications ? "Show less" : `Show more (${hiddenApplicationCount})`}
                </button>
              </div>
            )}
          </>
        )}
      </div>
      <FraudReviewSection />
    </section>
  );
}

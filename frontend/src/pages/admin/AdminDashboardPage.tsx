import { useEffect, useMemo, useState } from "react";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type { CreditApplication, CreditApplicationStatus, LoanProductType } from "../../types";
import { FraudReviewSection } from "./FraudReviewSection";

const PRODUCT_RATE_DEFAULTS: Record<LoanProductType, string> = {
  PERSONAL_LOAN: "9.90",
  MORTGAGE: "6.80",
  AUTO_LOAN: "8.40",
  STUDENT_LOAN: "5.90",
  HOME_IMPROVEMENT: "8.20",
  DEBT_CONSOLIDATION: "10.50",
};

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

export function AdminDashboardPage() {
  const { accessToken, logout, user } = useAuth();
  const [applications, setApplications] = useState<CreditApplication[]>([]);
  const [offerDrafts, setOfferDrafts] = useState<Record<string, { amount: string; rate: string }>>({});
  const [decisionApplicationId, setDecisionApplicationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const pendingApplications = useMemo(
    () => applications.filter((application) => application.status === "PENDING" || application.status === "DRAFT"),
    [applications],
  );

  async function loadApplications(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiRequest<CreditApplication[]>("/credit/admin/applications", { token });
      setApplications(response);
      setOfferDrafts(
        Object.fromEntries(
          response.map((application) => [
            application.id,
            {
              amount: application.offered_amount ?? application.requested_amount,
              rate: application.offered_interest_rate ?? defaultRate(application),
            },
          ]),
        ),
      );
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

  function updateDraft(applicationId: string, updates: Partial<{ amount: string; rate: string }>) {
    setOfferDrafts((current) => ({
      ...current,
      [applicationId]: {
        amount: current[applicationId]?.amount ?? "",
        rate: current[applicationId]?.rate ?? "",
        ...updates,
      },
    }));
  }

  async function decideApplication(application: CreditApplication, status: "APPROVED" | "REJECTED") {
    if (!accessToken || decisionApplicationId) return;
    setDecisionApplicationId(application.id);
    setError(null);
    const draft = offerDrafts[application.id] ?? { amount: application.requested_amount, rate: "9.50" };
    try {
      const updated = await apiRequest<CreditApplication>(`/credit/admin/applications/${application.id}/decision`, {
        method: "PATCH",
        token: accessToken,
        body:
          status === "APPROVED"
            ? { status, offered_amount: draft.amount, offered_interest_rate: draft.rate }
            : { status },
      });
      setApplications((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not update loan application.");
    } finally {
      setDecisionApplicationId(null);
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

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Admin dashboard</span>
          <span className="tag tag--neutral">{pendingApplications.length} pending credit</span>
        </div>
        {error && <p style={{ color: "var(--color-warning)", margin: "0 0 0.85rem" }}>{error}</p>}
        {isLoading && <div className="card-empty">Loading loan applications...</div>}
        {!isLoading && (
          <table>
            <thead>
              <tr>
                <th>Applicant</th>
                <th>Product</th>
                <th>Requested</th>
                <th>Offer</th>
                <th>Rate</th>
                <th>Score</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((application) => {
                const isOpen = application.status === "PENDING" || application.status === "DRAFT";
                const draft = offerDrafts[application.id] ?? {
                  amount: application.requested_amount,
                  rate: defaultRate(application),
                };
                return (
                  <tr key={application.id}>
                    <td>{application.user_id.slice(0, 8)}</td>
                    <td>{formatProductType(application.loan_product_type)}</td>
                    <td>{formatMoney(application.requested_amount, application.currency)}</td>
                    <td>
                      {isOpen ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <input
                            value={draft.amount}
                            onChange={(event) => updateDraft(application.id, { amount: event.target.value })}
                            inputMode="decimal"
                            style={{ minWidth: "8rem" }}
                          />
                          <span className="tag tag--outline">{application.currency}</span>
                        </div>
                      ) : (
                        formatMoney(application.offered_amount, application.currency)
                      )}
                    </td>
                    <td>
                      {isOpen ? (
                        <input
                          value={draft.rate}
                          onChange={(event) => updateDraft(application.id, { rate: event.target.value })}
                          inputMode="decimal"
                          style={{ minWidth: "6rem" }}
                        />
                      ) : (
                        application.offered_interest_rate ?? "N/A"
                      )}
                    </td>
                    <td>{application.credit_score_at_application}</td>
                    <td>
                      <span className={statusClass(application.status)}>{application.status}</span>
                    </td>
                    <td>
                      {isOpen ? (
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
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
                            onClick={() => decideApplication(application, "REJECTED")}
                            disabled={decisionApplicationId === application.id}
                          >
                            Reject
                          </button>
                        </div>
                      ) : (
                        <span>{application.resolved_at ? new Date(application.resolved_at).toLocaleDateString() : "N/A"}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {applications.length === 0 && (
                <tr>
                  <td colSpan={8}>No loan applications yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
      <FraudReviewSection />
    </section>
  );
}

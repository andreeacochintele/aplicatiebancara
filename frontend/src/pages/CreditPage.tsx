import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { ApiError, apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type {
  CreditApplication,
  CreditApplicationType,
  CreditProfile,
  CreditScore,
  Loan,
  LoanCalculatorResult,
} from "../types";

const APPLICATION_TYPES: CreditApplicationType[] = ["PERSONAL_LOAN", "CREDIT_CARD"];
const CREDIT_CURRENCIES = ["RON", "EUR", "USD", "GBP"];

function bandClass(band: string): string {
  if (band === "EXCELLENT" || band === "VERY_GOOD" || band === "GOOD") return "tag tag--accent";
  if (band === "FAIR") return "tag tag--neutral";
  return "tag tag--warning";
}

function formatFactorLabel(key: string): string {
  return key
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatApplicationType(type: CreditApplicationType): string {
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatMoney(value: string, currency = "RON"): string {
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

export function CreditPage() {
  const { accessToken, logout } = useAuth();
  const [profile, setProfile] = useState<CreditProfile | null>(null);
  const [score, setScore] = useState<CreditScore | null>(null);
  const [applications, setApplications] = useState<CreditApplication[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [income, setIncome] = useState("");
  const [existingDebt, setExistingDebt] = useState("");
  const [applicationType, setApplicationType] = useState<CreditApplicationType>("PERSONAL_LOAN");
  const [requestedAmount, setRequestedAmount] = useState("");
  const [requestedCurrency, setRequestedCurrency] = useState("RON");
  const [requestedTermMonths, setRequestedTermMonths] = useState("48");
  const [loanPrincipal, setLoanPrincipal] = useState("50000");
  const [loanCurrency, setLoanCurrency] = useState("RON");
  const [loanRate, setLoanRate] = useState("8.5");
  const [loanTerm, setLoanTerm] = useState("60");
  const [loanResult, setLoanResult] = useState<LoanCalculatorResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [isCalculatingLoan, setIsCalculatingLoan] = useState(false);
  const [activatingApplicationId, setActivatingApplicationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadWarning, setLoadWarning] = useState<string | null>(null);

  const scorePercent = useMemo(() => {
    if (!score) return 0;
    return Math.round(((score.score - 300) / 550) * 100);
  }, [score]);

  async function loadCreditData(token: string) {
    setIsLoading(true);
    setError(null);
    setLoadWarning(null);
    try {
      const [profileResponse, scoreResponse] = await Promise.all([
        apiRequest<CreditProfile>("/credit/profile", { token }),
        apiRequest<CreditScore>("/credit/score", { token }),
      ]);
      setProfile(profileResponse);
      setScore(scoreResponse);
      setIncome(profileResponse.income);
      setExistingDebt(profileResponse.existing_debt);

      const [applicationsResult, loansResult] = await Promise.allSettled([
        apiRequest<CreditApplication[]>("/credit/applications", { token }),
        apiRequest<Loan[]>("/credit/loans", { token }),
      ]);

      if (applicationsResult.status === "fulfilled") {
        setApplications(applicationsResult.value);
      } else {
        setApplications([]);
        setLoadWarning("Credit score loaded, but credit applications could not be loaded.");
      }

      if (loansResult.status === "fulfilled") {
        setLoans(loansResult.value);
      } else {
        setLoans([]);
        setLoadWarning("Credit score loaded, but active loans could not be loaded.");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not load credit score.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken) return;
    void loadCreditData(accessToken);
  }, [accessToken, logout]);

  async function recalculateScore() {
    if (!accessToken || isSaving) return;
    setIsSaving(true);
    setError(null);
    try {
      const scoreResponse = await apiRequest<CreditScore>("/credit/score/recalculate", {
        method: "POST",
        token: accessToken,
        body: {
          income: income || null,
          existing_debt: existingDebt || null,
        },
      });
      const profileResponse = await apiRequest<CreditProfile>("/credit/profile", { token: accessToken });
      setScore(scoreResponse);
      setProfile(profileResponse);
      setIncome(profileResponse.income);
      setExistingDebt(profileResponse.existing_debt);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not recalculate score.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createApplication() {
    if (!accessToken || isApplying) return;
    setIsApplying(true);
    setError(null);
    try {
      const application = await apiRequest<CreditApplication>("/credit/applications", {
        method: "POST",
        token: accessToken,
        body: {
          type: applicationType,
          requested_amount: requestedAmount,
          currency: requestedCurrency,
          requested_term_months: applicationType === "PERSONAL_LOAN" ? Number(requestedTermMonths) : null,
        },
      });
      setApplications((current) => [application, ...current]);
      setRequestedAmount("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not create credit application.");
    } finally {
      setIsApplying(false);
    }
  }

  async function activateLoan(application: CreditApplication) {
    if (!accessToken || activatingApplicationId) return;
    setActivatingApplicationId(application.id);
    setError(null);
    try {
      const loan = await apiRequest<Loan>(`/credit/applications/${application.id}/loan`, {
        method: "POST",
        token: accessToken,
      });
      setLoans((current) => [loan, ...current]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not activate loan.");
    } finally {
      setActivatingApplicationId(null);
    }
  }

  async function calculateLoan() {
    if (!accessToken || isCalculatingLoan) return;
    setIsCalculatingLoan(true);
    setError(null);
    try {
      const result = await apiRequest<LoanCalculatorResult>("/credit/loan-calculator", {
        method: "POST",
        token: accessToken,
        body: {
          principal_amount: loanPrincipal,
          currency: loanCurrency,
          annual_interest_rate: loanRate,
          term_months: Number(loanTerm),
        },
      });
      setLoanResult(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not calculate loan preview.");
    } finally {
      setIsCalculatingLoan(false);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Credit score</span>
          {score && <span className={bandClass(score.band)}>{score.band}</span>}
        </div>

        {isLoading && <div className="card-empty">Loading credit score...</div>}
        {!isLoading && score && (
          <div className="credit-score-layout">
            <div>
              <div className="credit-score-ring" style={{ "--score-percent": `${scorePercent}%` } as CSSProperties}>
                <div>
                  <span>{score.score}</span>
                  <small>/ 850</small>
                </div>
              </div>
            </div>
            <div className="credit-factor-grid">
              {Object.entries(score.reason_data).map(([key, value]) => (
                <div className="credit-factor" key={key}>
                  <div className="eyebrow">{formatFactorLabel(key)}</div>
                  <div className="card-panel__value">{value}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Loan calculator</span>
        </div>
        <div className="loan-calculator-layout">
          <div className="loan-calculator-form">
            <label>
              Principal amount
              <input
                value={loanPrincipal}
                onChange={(event) => setLoanPrincipal(event.target.value)}
                inputMode="decimal"
              />
            </label>
            <label>
              Currency
              <select value={loanCurrency} onChange={(event) => setLoanCurrency(event.target.value)}>
                {CREDIT_CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Annual interest rate
              <input value={loanRate} onChange={(event) => setLoanRate(event.target.value)} inputMode="decimal" />
            </label>
            <label>
              Term months
              <input value={loanTerm} onChange={(event) => setLoanTerm(event.target.value)} inputMode="numeric" />
            </label>
            <button type="button" onClick={calculateLoan} disabled={isCalculatingLoan}>
              {isCalculatingLoan ? "Calculating..." : "Calculate"}
            </button>
          </div>

          {loanResult && (
            <div className="loan-result">
              <div className="loan-result-grid">
                <div>
                  <span className="eyebrow">Monthly payment</span>
                  <strong>{formatMoney(loanResult.monthly_payment, loanResult.currency)}</strong>
                </div>
                <div>
                  <span className="eyebrow">Total interest</span>
                  <strong>{formatMoney(loanResult.total_interest, loanResult.currency)}</strong>
                </div>
                <div>
                  <span className="eyebrow">Total payment</span>
                  <strong>{formatMoney(loanResult.total_payment, loanResult.currency)}</strong>
                </div>
              </div>
              <table className="loan-schedule-table">
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Payment</th>
                    <th>Principal</th>
                    <th>Interest</th>
                    <th>Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {loanResult.schedule.slice(0, 6).map((item) => (
                    <tr key={item.installment_number}>
                      <td>{item.installment_number}</td>
                      <td>{formatMoney(item.payment_amount, loanResult.currency)}</td>
                      <td>{formatMoney(item.principal_amount, loanResult.currency)}</td>
                      <td>{formatMoney(item.interest_amount, loanResult.currency)}</td>
                      <td>{formatMoney(item.remaining_principal, loanResult.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Active loans</span>
        </div>
        {loadWarning && <p style={{ color: "var(--color-warning)", margin: "0 0 0.85rem" }}>{loadWarning}</p>}
        <table>
          <thead>
            <tr>
              <th>Principal</th>
              <th>Monthly</th>
              <th>Outstanding</th>
              <th>Next payment</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {loans.map((loan) => (
              <tr key={loan.id}>
                <td>{formatMoney(loan.principal_amount, loan.currency)}</td>
                <td>{formatMoney(loan.monthly_payment, loan.currency)}</td>
                <td>{formatMoney(loan.outstanding_principal, loan.currency)}</td>
                <td>{new Date(loan.next_payment_date).toLocaleDateString()}</td>
                <td>
                  <span className={loan.status === "ACTIVE" ? "tag tag--accent" : "tag tag--neutral"}>
                    {loan.status}
                  </span>
                </td>
              </tr>
            ))}
            {!isLoading && loans.length === 0 && (
              <tr>
                <td colSpan={5}>No active loans yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Mock profile inputs</span>
        </div>
        <div className="credit-form-grid">
          <label>
            Monthly income
            <input value={income} onChange={(event) => setIncome(event.target.value)} inputMode="decimal" />
          </label>
          <label>
            Existing debt
            <input value={existingDebt} onChange={(event) => setExistingDebt(event.target.value)} inputMode="decimal" />
          </label>
          <button type="button" onClick={recalculateScore} disabled={isSaving}>
            {isSaving ? "Recalculating..." : "Recalculate score"}
          </button>
        </div>
        {profile && (
          <div className="credit-profile-meta">
            <span>Last updated</span>
            <strong>{new Date(profile.updated_at).toLocaleString()}</strong>
          </div>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Credit applications</span>
        </div>
        <div className="credit-application-form">
          <label>
            Product
            <select
              value={applicationType}
              onChange={(event) => setApplicationType(event.target.value as CreditApplicationType)}
            >
              {APPLICATION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {formatApplicationType(type)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Requested amount
            <input
              value={requestedAmount}
              onChange={(event) => setRequestedAmount(event.target.value)}
              inputMode="decimal"
            />
          </label>
          <label>
            Currency
            <select value={requestedCurrency} onChange={(event) => setRequestedCurrency(event.target.value)}>
              {CREDIT_CURRENCIES.map((currency) => (
                <option key={currency} value={currency}>
                  {currency}
                </option>
              ))}
            </select>
          </label>
          {applicationType === "PERSONAL_LOAN" && (
            <label>
              Term months
              <input
                value={requestedTermMonths}
                onChange={(event) => setRequestedTermMonths(event.target.value)}
                inputMode="numeric"
              />
            </label>
          )}
          <button type="button" onClick={createApplication} disabled={isApplying}>
            {isApplying ? "Submitting..." : "Submit application"}
          </button>
        </div>

        <table style={{ marginTop: "1rem" }}>
          <thead>
            <tr>
              <th>Type</th>
              <th>Amount</th>
              <th>Term</th>
              <th>Score</th>
              <th>Status</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {applications.map((application) => {
              const existingLoan = loans.find((loan) => loan.application_id === application.id);
              const canActivate =
                application.type === "PERSONAL_LOAN" && application.status === "APPROVED" && !existingLoan;
              return (
                <tr key={application.id}>
                  <td>{formatApplicationType(application.type)}</td>
                  <td>{formatMoney(application.requested_amount, application.currency)}</td>
                  <td>{application.requested_term_months ?? "N/A"}</td>
                  <td>{application.credit_score_at_application}</td>
                  <td>
                    <span className={application.status === "PENDING" ? "tag tag--neutral" : "tag tag--accent"}>
                      {application.status}
                    </span>
                  </td>
                  <td>{new Date(application.created_at).toLocaleDateString()}</td>
                  <td>
                    {existingLoan ? (
                      <span className="tag tag--accent">Loan active</span>
                    ) : (
                      <button
                        type="button"
                        className="button--ghost"
                        onClick={() => activateLoan(application)}
                        disabled={!canActivate || activatingApplicationId === application.id}
                      >
                        {activatingApplicationId === application.id ? "Activating..." : "Activate loan"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {!isLoading && applications.length === 0 && (
              <tr>
                <td colSpan={7}>No credit applications yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

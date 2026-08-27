import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { Download } from "lucide-react";
import { ApiError, apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type {
  Card,
  CreditApplication,
  CreditDocument,
  CreditDocumentPurpose,
  CreditProfile,
  CreditScore,
  EarlyRepaymentPaymentResult,
  EarlyRepaymentResult,
  Loan,
  LoanCalculatorResult,
  LoanAutopayUpdate,
  LoanInstallment,
  LoanProduct,
  LoanProductType,
  Wallet,
} from "../types";

const CREDIT_CURRENCIES = ["RON", "EUR", "USD", "GBP"];
const DOWN_PAYMENT_LOAN_TYPES = new Set<LoanProductType>(["MORTGAGE", "AUTO_LOAN", "HOME_IMPROVEMENT"]);

type PaymentPlanExportRow = {
  number: number;
  dueDate: string | null;
  paymentAmount: string;
  principalAmount: string;
  interestAmount: string;
  remainingPrincipal: string;
  status: string | null;
};

const DEFAULT_LOAN_PRODUCTS: LoanProduct[] = [
  {
    product_type: "PERSONAL_LOAN",
    name: "Personal loan",
    description: "Unsecured instalment loan for general personal expenses.",
    representative_apr: "9.90",
    borrowing_rate_note: "Demo fixed annual borrowing rate; final offer depends on score, term, amount and currency.",
    typical_term_months: "12-60 months",
    fees: ["Possible administration fee", "Late payment interest may apply", "Early repayment compensation may apply"],
    obligations: ["Repay monthly instalments on the agreed due dates.", "Review pre-contractual information before accepting an offer."],
    liabilities: ["Late or missed payments can generate additional costs.", "Persistent non-payment can lead to collections or legal recovery."],
    required_documents: ["Proof of identity", "Proof of income", "Bank account history"],
    collateral_required: false,
    insurance_required: false,
  },
];

const LOAN_PRODUCT_CONTEXT: Record<LoanProductType, { focus: string; risk: string; accent: string }> = {
  PERSONAL_LOAN: {
    focus: "Flexible unsecured borrowing for general expenses.",
    risk: "Higher pricing than secured credit because no collateral backs the loan.",
    accent: "Everyday flexibility",
  },
  MORTGAGE: {
    focus: "Large, long-term property financing with collateral and heavier documentation.",
    risk: "The property can be enforced after serious default, and variable rates can raise instalments.",
    accent: "Property secured",
  },
  AUTO_LOAN: {
    focus: "Vehicle purchase financing, often linked to the car invoice and insurance.",
    risk: "If secured, the vehicle can be repossessed and the borrower may still owe a shortfall.",
    accent: "Vehicle purchase",
  },
  STUDENT_LOAN: {
    focus: "Education funding with study-related documents and possible guarantor checks.",
    risk: "Deferred or grace-period interest can still accrue before full repayment starts.",
    accent: "Education focused",
  },
  HOME_IMPROVEMENT: {
    focus: "Renovation or repair funding, usually tied to estimates, invoices or project scope.",
    risk: "Project overruns do not reduce repayment responsibility.",
    accent: "Renovation project",
  },
  DEBT_CONSOLIDATION: {
    focus: "Combines multiple debts into one repayment schedule.",
    risk: "A lower monthly payment can still cost more overall if the term is extended.",
    accent: "Debt refinance",
  },
};

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

function formatProductType(type: LoanProductType | null): string {
  if (!type) return "Mortgage";
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatMoney(value: string, currency = "RON"): string {
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function escapeExcelCell(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatExcelNumber(value: string): string {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue.toFixed(2) : "0.00";
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("Could not read selected document."));
    reader.readAsDataURL(file);
  });
}

function parseAmount(value: string): number {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : 0;
}

function walletDisplayName(wallet: Wallet): string {
  return `${wallet.currency}${wallet.is_main ? " - Main" : ""}`;
}

function ListPreview({ items }: { items: string[] }) {
  return (
    <ul>
      {items.slice(0, 3).map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function CreditPage() {
  const { accessToken, logout } = useAuth();
  const [profile, setProfile] = useState<CreditProfile | null>(null);
  const [score, setScore] = useState<CreditScore | null>(null);
  const [applications, setApplications] = useState<CreditApplication[]>([]);
  const [creditDocuments, setCreditDocuments] = useState<CreditDocument[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [areLoansLoaded, setAreLoansLoaded] = useState(false);
  const [applicationBreakdowns, setApplicationBreakdowns] = useState<Record<string, LoanCalculatorResult>>({});
  const [earlyRepaymentAmounts, setEarlyRepaymentAmounts] = useState<Record<string, string>>({});
  const [earlyRepaymentSourceIds, setEarlyRepaymentSourceIds] = useState<Record<string, string>>({});
  const [autopaySourceIds, setAutopaySourceIds] = useState<Record<string, string>>({});
  const [autopayDates, setAutopayDates] = useState<Record<string, string>>({});
  const [autopayAmounts, setAutopayAmounts] = useState<Record<string, string>>({});
  const [configuringAutopayLoanIds, setConfiguringAutopayLoanIds] = useState<Set<string>>(() => new Set());
  const [earlyRepaymentResults, setEarlyRepaymentResults] = useState<Record<string, EarlyRepaymentResult>>({});
  const [earlyRepaymentErrors, setEarlyRepaymentErrors] = useState<Record<string, string>>({});
  const [earlyRepaymentMessages, setEarlyRepaymentMessages] = useState<Record<string, string>>({});
  const [loanProducts, setLoanProducts] = useState<LoanProduct[]>(DEFAULT_LOAN_PRODUCTS);
  const [income, setIncome] = useState("");
  const [existingDebt, setExistingDebt] = useState("");
  const [profileCurrency, setProfileCurrency] = useState("RON");
  const [supportingDocuments, setSupportingDocuments] = useState<File[]>([]);
  const [loanApplicationDocuments, setLoanApplicationDocuments] = useState<File[]>([]);
  const [additionalLoanDocuments, setAdditionalLoanDocuments] = useState<Record<string, File[]>>({});
  const [documentMessage, setDocumentMessage] = useState<string | null>(null);
  const [loanPrompt, setLoanPrompt] = useState<string | null>(null);
  const [loanProductType, setLoanProductType] = useState<LoanProductType>("PERSONAL_LOAN");
  const [isLoanInfoExpanded, setIsLoanInfoExpanded] = useState(false);
  const [areApprovedOffersExpanded, setAreApprovedOffersExpanded] = useState(false);
  const [arePastLoansExpanded, setArePastLoansExpanded] = useState(false);
  const [expandedOfferIds, setExpandedOfferIds] = useState<Set<string>>(() => new Set());
  const [expandedPaymentPlanIds, setExpandedPaymentPlanIds] = useState<Set<string>>(() => new Set());
  const [loanInstallmentsByLoanId, setLoanInstallmentsByLoanId] = useState<Record<string, LoanInstallment[]>>({});
  const [loadingPaymentPlanLoanId, setLoadingPaymentPlanLoanId] = useState<string | null>(null);
  const [paymentPlanErrors, setPaymentPlanErrors] = useState<Record<string, string>>({});
  const [requestedAmount, setRequestedAmount] = useState("");
  const [assetPrice, setAssetPrice] = useState("");
  const [downPayment, setDownPayment] = useState("");
  const [requestedCurrency, setRequestedCurrency] = useState("RON");
  const [requestedTermMonths, setRequestedTermMonths] = useState("48");
  const [applicationEstimate, setApplicationEstimate] = useState<LoanCalculatorResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreditDetailsLoading, setIsCreditDetailsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [isEstimatingApplication, setIsEstimatingApplication] = useState(false);
  const [activatingApplicationId, setActivatingApplicationId] = useState<string | null>(null);
  const [uploadingMoreInfoApplicationId, setUploadingMoreInfoApplicationId] = useState<string | null>(null);
  const [simulatingLoanId, setSimulatingLoanId] = useState<string | null>(null);
  const [payingLoanId, setPayingLoanId] = useState<string | null>(null);
  const [updatingAutopayLoanId, setUpdatingAutopayLoanId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadWarning, setLoadWarning] = useState<string | null>(null);

  const hasPendingScoreReview = useMemo(
    () =>
      creditDocuments.some(
        (document) => document.purpose === "CREDIT_SCORE" && ["UPLOADED", "NEEDS_MORE_INFO"].includes(document.status),
      ),
    [creditDocuments],
  );
  const scoreIsPendingAdminReview = score?.reason_data.review_status === "PENDING_ADMIN_REVIEW";
  const visibleScore = score && !scoreIsPendingAdminReview ? score : null;
  const scorePercent = useMemo(() => {
    if (!visibleScore) return 0;
    return Math.round(((visibleScore.score - 300) / 550) * 100);
  }, [visibleScore]);

  const selectedLoanProduct = useMemo(
    () => loanProducts.find((product) => product.product_type === loanProductType) ?? loanProducts[0],
    [loanProductType, loanProducts],
  );

  const visibleLoanApplications = useMemo(
    () =>
      applications.filter(
        (application) =>
          application.type === "PERSONAL_LOAN" &&
          (application.status === "APPROVED" || application.status === "PENDING"),
      ),
    [applications],
  );
  const activeLoanApplications = useMemo(
    () =>
      visibleLoanApplications.filter((application) => {
        const existingLoan = loans.find((loan) => loan.application_id === application.id);
        if (existingLoan) return existingLoan.status !== "PAID" && existingLoan.status !== "CLOSED";
        return areLoansLoaded && application.status === "APPROVED" ? true : application.status === "PENDING";
      }),
    [areLoansLoaded, loans, visibleLoanApplications],
  );
  const closedLoanApplications = useMemo(
    () =>
      areLoansLoaded
        ? visibleLoanApplications.filter((application) => {
            const existingLoan = loans.find((loan) => loan.application_id === application.id);
            return existingLoan?.status === "PAID" || existingLoan?.status === "CLOSED";
          })
        : [],
    [areLoansLoaded, loans, visibleLoanApplications],
  );
  const documentsByApplication = useMemo(
    () =>
      creditDocuments.reduce<Record<string, CreditDocument[]>>((groups, document) => {
        if (!document.application_id) return groups;
        groups[document.application_id] = [...(groups[document.application_id] ?? []), document];
        return groups;
      }, {}),
    [creditDocuments],
  );
  const activeWallets = useMemo(() => wallets.filter((wallet) => wallet.status === "ACTIVE"), [wallets]);
  const activeDebitCards = useMemo(
    () => cards.filter((card) => card.type === "DEBIT" && card.status === "ACTIVE" && card.default_wallet_id),
    [cards],
  );
  const activeCreditCards = useMemo(
    () => cards.filter((card) => card.type === "CREDIT" && card.status === "ACTIVE" && card.credit_account),
    [cards],
  );
  const debitRepresentedWalletIds = useMemo(
    () => new Set(activeDebitCards.map((card) => card.default_wallet_id).filter((walletId): walletId is string => Boolean(walletId))),
    [activeDebitCards],
  );
  const directPaymentWallets = useMemo(
    () => activeWallets.filter((wallet) => !debitRepresentedWalletIds.has(wallet.id)),
    [activeWallets, debitRepresentedWalletIds],
  );
  const supportsDownPayment = DOWN_PAYMENT_LOAN_TYPES.has(loanProductType);
  const existingLoanDebt = useMemo(
    () =>
      loans
        .filter((loan) => loan.status === "ACTIVE")
        .reduce((total, loan) => total + Number(loan.outstanding_principal), 0),
    [loans],
  );
  const existingLoanDebtDisplay = existingLoanDebt.toFixed(2);
  const assetPriceAmount = parseAmount(assetPrice);
  const downPaymentAmount = parseAmount(downPayment);
  const financedAmount = supportsDownPayment ? Math.max(0, assetPriceAmount - downPaymentAmount) : parseAmount(requestedAmount);
  const principalAmountForApplication = financedAmount > 0 ? financedAmount.toFixed(2) : "";
  const hasDownPaymentError = supportsDownPayment && downPaymentAmount > assetPriceAmount && assetPriceAmount > 0;
  const canSubmitApplication =
    !isApplying &&
    principalAmountForApplication !== "" &&
    Number(requestedTermMonths) > 0 &&
    !hasDownPaymentError &&
    loanApplicationDocuments.length > 0;

  async function loadCreditData(token: string) {
    setIsLoading(true);
    setError(null);
    setLoadWarning(null);
    setAreLoansLoaded(false);
    try {
      const [profileResponse, scoreResponse] = await Promise.all([
        apiRequest<CreditProfile>("/credit/profile", { token }),
        apiRequest<CreditScore>("/credit/score", { token }),
      ]);
      setProfile(profileResponse);
      setScore(scoreResponse);
      setIncome(profileResponse.income);
      setExistingDebt(profileResponse.existing_debt);
      setProfileCurrency(profileResponse.currency);
      setIsLoading(false);
      setIsCreditDetailsLoading(true);

      const [applicationsResult, loansResult, loanProductsResult, walletsResult, cardsResult, documentsResult] = await Promise.allSettled([
        apiRequest<CreditApplication[]>("/credit/applications", { token }),
        apiRequest<Loan[]>("/credit/loans", { token }),
        apiRequest<LoanProduct[]>("/credit/loan-products", { token }),
        apiRequest<Wallet[]>("/wallets", { token }),
        apiRequest<Card[]>("/cards", { token }),
        apiRequest<CreditDocument[]>("/credit/documents", { token }),
      ]);

      if (applicationsResult.status === "fulfilled") {
        setApplications(applicationsResult.value);
      } else {
        setApplications([]);
        setLoadWarning("Credit score loaded, but loan applications could not be loaded.");
      }

      if (loansResult.status === "fulfilled") {
        setAreLoansLoaded(true);
        setLoans(loansResult.value);
        setLoanInstallmentsByLoanId({});
        const loanDebt = loansResult.value
          .filter((loan) => loan.status === "ACTIVE")
          .reduce((total, loan) => total + Number(loan.outstanding_principal), 0);
        setExistingDebt(loanDebt.toFixed(2));
      } else {
        setAreLoansLoaded(false);
        setLoans([]);
        setLoadWarning("Credit score loaded, but active loans could not be loaded.");
      }

      if (loanProductsResult.status === "fulfilled" && loanProductsResult.value.length > 0) {
        setLoanProducts(loanProductsResult.value);
      }

      if (walletsResult.status === "fulfilled") {
        setWallets(walletsResult.value);
      } else {
        setWallets([]);
      }

      if (cardsResult.status === "fulfilled") {
        setCards(cardsResult.value);
      } else {
        setCards([]);
      }

      if (documentsResult.status === "fulfilled") {
        setCreditDocuments(documentsResult.value);
      } else {
        setCreditDocuments([]);
      }

    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not load credit score.");
    } finally {
      setIsLoading(false);
      setIsCreditDetailsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken) return;
    void loadCreditData(accessToken);
  }, [accessToken, logout]);

  useEffect(() => {
    setExistingDebt(existingLoanDebtDisplay);
  }, [existingLoanDebtDisplay]);

  useEffect(() => {
    if (!accessToken || applications.length === 0) return;
    void loadApplicationBreakdowns(accessToken, applications);
  }, [accessToken, applications]);

  useEffect(() => {
    if (!accessToken || !selectedLoanProduct) return;
    const amount = financedAmount;
    const termMonths = Number(requestedTermMonths);
    if (!Number.isFinite(amount) || amount <= 0 || !Number.isFinite(termMonths) || termMonths <= 0) {
      setApplicationEstimate(null);
      setIsEstimatingApplication(false);
      return;
    }

    const timeout = window.setTimeout(() => {
      setIsEstimatingApplication(true);
      apiRequest<LoanCalculatorResult>("/credit/loan-calculator", {
        method: "POST",
        token: accessToken,
        body: {
          principal_amount: principalAmountForApplication,
          currency: requestedCurrency,
          annual_interest_rate: selectedLoanProduct.representative_apr,
          term_months: termMonths,
        },
      })
        .then((estimate) => setApplicationEstimate(estimate))
        .catch(() => setApplicationEstimate(null))
        .finally(() => setIsEstimatingApplication(false));
    }, 250);

    return () => window.clearTimeout(timeout);
  }, [accessToken, financedAmount, principalAmountForApplication, requestedCurrency, requestedTermMonths, selectedLoanProduct]);

  async function loadApplicationBreakdowns(token: string, applicationList: CreditApplication[]) {
    const approvedApplications = applicationList.filter(
      (application) =>
        application.status === "APPROVED" &&
        application.offered_amount &&
        application.offered_interest_rate &&
        application.requested_term_months,
    );

    if (approvedApplications.length === 0) {
      setApplicationBreakdowns({});
      return;
    }

    const results = await Promise.allSettled(
      approvedApplications.map(async (application) => {
        const breakdown = await apiRequest<LoanCalculatorResult>("/credit/loan-calculator", {
          method: "POST",
          token,
          body: {
            principal_amount: application.offered_amount,
            currency: application.currency,
            annual_interest_rate: application.offered_interest_rate,
            term_months: application.requested_term_months,
          },
        });
        return [application.id, breakdown] as const;
      }),
    );

    setApplicationBreakdowns(
      Object.fromEntries(
        results
          .filter((result): result is PromiseFulfilledResult<readonly [string, LoanCalculatorResult]> => result.status === "fulfilled")
          .map((result) => result.value),
      ),
    );
  }

  function toggleApprovedOfferDetails(applicationId: string) {
    setExpandedOfferIds((current) => {
      const next = new Set(current);
      if (next.has(applicationId)) {
        next.delete(applicationId);
      } else {
        next.add(applicationId);
      }
      return next;
    });
  }

  async function togglePaymentPlan(applicationId: string, loan?: Loan) {
    const isOpen = expandedPaymentPlanIds.has(applicationId);
    setExpandedPaymentPlanIds((current) => {
      const next = new Set(current);
      if (isOpen) {
        next.delete(applicationId);
      } else {
        next.add(applicationId);
      }
      return next;
    });
    if (isOpen || !loan || loanInstallmentsByLoanId[loan.id] || loadingPaymentPlanLoanId === loan.id || !accessToken) return;

    setLoadingPaymentPlanLoanId(loan.id);
    setPaymentPlanErrors((current) => {
      const next = { ...current };
      delete next[applicationId];
      return next;
    });
    try {
      const installments = await apiRequest<LoanInstallment[]>(`/credit/loans/${loan.id}/installments`, { token: accessToken });
      setLoanInstallmentsByLoanId((current) => ({ ...current, [loan.id]: installments }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setPaymentPlanErrors((current) => ({
        ...current,
        [applicationId]: err instanceof ApiError ? err.message : "Could not load payment plan.",
      }));
    } finally {
      setLoadingPaymentPlanLoanId(null);
    }
  }

  function downloadPaymentPlan(
    application: CreditApplication,
    breakdown: LoanCalculatorResult,
    rows: PaymentPlanExportRow[],
  ) {
    if (rows.length === 0) return;

    const amount = application.offered_amount ?? application.requested_amount;
    const generatedAt = new Date().toLocaleString();
    const title = `Loan payment plan - ${formatMoney(amount, application.currency)}`;
    const tableRows = rows
      .map((installment) => {
        const dueDate = installment.dueDate ? new Date(installment.dueDate).toLocaleDateString() : "";
        return `<tr>
          <td>${installment.number}</td>
          <td>${escapeExcelCell(dueDate)}</td>
          <td>${formatExcelNumber(installment.paymentAmount)}</td>
          <td>${formatExcelNumber(installment.principalAmount)}</td>
          <td>${formatExcelNumber(installment.interestAmount)}</td>
          <td>${formatExcelNumber(installment.remainingPrincipal)}</td>
          <td>${escapeExcelCell(installment.status ?? "")}</td>
        </tr>`;
      })
      .join("");
    const workbook = `<!doctype html>
      <html>
        <head>
          <meta charset="utf-8" />
          <style>
            table { border-collapse: collapse; font-family: Arial, sans-serif; }
            th, td { border: 1px solid #999; padding: 6px 8px; }
            th { background: #eef2ff; font-weight: 700; }
          </style>
        </head>
        <body>
          <h2>${escapeExcelCell(title)}</h2>
          <p>Generated: ${escapeExcelCell(generatedAt)}</p>
          <p>APR: ${escapeExcelCell(String(application.offered_interest_rate ?? breakdown.annual_interest_rate))}%</p>
          <p>Term: ${breakdown.term_months} months</p>
          <p>Currency: ${escapeExcelCell(breakdown.currency)}</p>
          <table>
            <thead>
              <tr>
                <th>Payment #</th>
                <th>Due date</th>
                <th>Payment amount</th>
                <th>Principal</th>
                <th>Interest</th>
                <th>Remaining principal</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>${tableRows}</tbody>
          </table>
        </body>
      </html>`;
    const blob = new Blob([workbook], { type: "application/vnd.ms-excel;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const safeAmount = amount.replace(/[^0-9a-z]/gi, "");
    link.href = url;
    link.download = `loan_payment_plan_${safeAmount || "loan"}_${breakdown.currency}.xls`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function loanPaymentSourceOptions(currency: string) {
    return [
      ...activeDebitCards
        .map((card) => {
          const wallet = wallets.find((item) => item.id === card.default_wallet_id);
          return {
            value: `DEBIT_CARD:${card.id}`,
            walletId: wallet?.id ?? "",
            cardId: card.id,
            label: `Debit **** ${card.last_four}${wallet ? ` - ${walletDisplayName(wallet)}` : ""}`,
            currency: wallet?.currency,
            availableBalance: wallet?.available_balance ?? "0.00",
          };
        })
        .filter((source) => source.walletId && source.currency === currency),
      ...directPaymentWallets
        .filter((wallet) => wallet.currency === currency)
        .map((wallet) => ({
          value: `ACCOUNT:${wallet.id}`,
          walletId: wallet.id,
          cardId: null,
          label: `${walletDisplayName(wallet)} account`,
          currency: wallet.currency,
          availableBalance: wallet.available_balance,
        })),
      ...activeCreditCards
        .filter((card) => card.credit_account?.currency === currency)
        .map((card) => ({
          value: `CREDIT_CARD:${card.id}`,
          walletId: "",
          cardId: card.id,
          label: `Credit **** ${card.last_four}`,
          currency: card.credit_account?.currency,
          availableBalance: card.credit_account?.available_credit ?? "0.00",
        })),
    ];
  }

  function loanAutopaySourceOptions(currency: string) {
    return loanPaymentSourceOptions(currency).filter((source) => !source.value.startsWith("CREDIT_CARD:"));
  }

  function loanAutopaySourceValue(loan: Loan): string {
    if (loan.autopay_source_card_id) return `DEBIT_CARD:${loan.autopay_source_card_id}`;
    if (loan.autopay_source_wallet_id) return `ACCOUNT:${loan.autopay_source_wallet_id}`;
    return "";
  }

  function loanAutopayDateValue(loan: Loan): string {
    const today = new Date().toISOString().slice(0, 10);
    const preferredDate = loan.autopay_next_run_on || loan.next_payment_date;
    return preferredDate < today ? today : preferredDate;
  }

  function loanAutopayAmountValue(loan: Loan): string {
    return loan.autopay_amount || loan.monthly_payment;
  }

  function openAutopayConfig(loan: Loan) {
    setAutopaySourceIds((current) => ({
      ...current,
      [loan.id]: current[loan.id] || loanAutopaySourceValue(loan),
    }));
    setAutopayDates((current) => ({
      ...current,
      [loan.id]: current[loan.id] || loanAutopayDateValue(loan),
    }));
    setAutopayAmounts((current) => ({
      ...current,
      [loan.id]: current[loan.id] || loanAutopayAmountValue(loan),
    }));
    setConfiguringAutopayLoanIds((current) => {
      const next = new Set(current);
      next.add(loan.id);
      return next;
    });
  }

  function closeAutopayConfig(loanId: string) {
    setConfiguringAutopayLoanIds((current) => {
      const next = new Set(current);
      next.delete(loanId);
      return next;
    });
  }

  async function updateLoanAutopay(loan: Loan, sourceOptions: ReturnType<typeof loanAutopaySourceOptions>, enabled: boolean) {
    if (!accessToken || updatingAutopayLoanId) return;

    const selectedSourceValue = autopaySourceIds[loan.id] || loanAutopaySourceValue(loan) || sourceOptions[0]?.value || "";
    const source = sourceOptions.find((option) => option.value === selectedSourceValue);
    const selectedDate = autopayDates[loan.id] || loanAutopayDateValue(loan);
    const selectedAmount = autopayAmounts[loan.id] || loanAutopayAmountValue(loan);
    if (enabled && !source) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: "No current account or debit card is available in this loan currency.",
      }));
      return;
    }
    if (enabled && !selectedDate) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: "Choose a recurring payment date.",
      }));
      return;
    }
    if (enabled && parseAmount(selectedAmount) <= 0) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: "Enter a positive recurring payment amount.",
      }));
      return;
    }

    setUpdatingAutopayLoanId(loan.id);
    setEarlyRepaymentErrors((current) => {
      const next = { ...current };
      delete next[loan.id];
      return next;
    });
    setEarlyRepaymentMessages((current) => {
      const next = { ...current };
      delete next[loan.id];
      return next;
    });

    try {
      const body: LoanAutopayUpdate = enabled
        ? {
            enabled: true,
            amount: selectedAmount,
            source_wallet_id: source?.walletId || null,
            source_card_id: source?.cardId || null,
            next_run_on: selectedDate,
          }
        : { enabled: false };
      const updatedLoan = await apiRequest<Loan>(`/credit/loans/${loan.id}/autopay`, {
        method: "PATCH",
        token: accessToken,
        body,
      });
      setLoans((current) => current.map((item) => (item.id === updatedLoan.id ? updatedLoan : item)));
      const [freshLoans, freshWallets, freshCards] = await Promise.all([
        apiRequest<Loan[]>("/credit/loans", { token: accessToken }),
        apiRequest<Wallet[]>("/wallets", { token: accessToken }),
        apiRequest<Card[]>("/cards", { token: accessToken }),
      ]);
      setLoans(freshLoans);
      setLoanInstallmentsByLoanId((current) => {
        const next = { ...current };
        delete next[loan.id];
        return next;
      });
      setWallets(freshWallets);
      setCards(freshCards);
      closeAutopayConfig(loan.id);
      setEarlyRepaymentMessages((current) => ({
        ...current,
        [loan.id]: enabled ? "Recurring loan payment enabled." : "Recurring loan payment disabled.",
      }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: err instanceof ApiError ? err.message : "Could not update recurring payment.",
      }));
    } finally {
      setUpdatingAutopayLoanId(null);
    }
  }

  async function simulateEarlyRepayment(loan: Loan) {
    if (!accessToken || simulatingLoanId) return;

    const extraPaymentAmount = earlyRepaymentAmounts[loan.id] ?? "";
    if (parseAmount(extraPaymentAmount) <= 0) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: "Enter a positive extra payment amount.",
      }));
      return;
    }

    setSimulatingLoanId(loan.id);
    setEarlyRepaymentErrors((current) => {
      const next = { ...current };
      delete next[loan.id];
      return next;
    });

    try {
      const result = await apiRequest<EarlyRepaymentResult>(`/credit/loans/${loan.id}/early-repayment-simulation`, {
        method: "POST",
        token: accessToken,
        body: {
          extra_payment_amount: extraPaymentAmount,
        },
      });
      setEarlyRepaymentResults((current) => ({
        ...current,
        [loan.id]: result,
      }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: err instanceof ApiError ? err.message : "Could not simulate early repayment.",
      }));
    } finally {
      setSimulatingLoanId(null);
    }
  }

  async function makeEarlyRepayment(loan: Loan, sourceOptions: ReturnType<typeof loanPaymentSourceOptions>) {
    if (!accessToken || payingLoanId) return;

    const amount = earlyRepaymentAmounts[loan.id] ?? "";
    const selectedSourceValue = earlyRepaymentSourceIds[loan.id] || sourceOptions[0]?.value || "";
    const source = sourceOptions.find((option) => option.value === selectedSourceValue);
    if (parseAmount(amount) <= 0) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: "Enter a positive payment amount.",
      }));
      return;
    }
    if (!source) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: "No payment source is available in this loan currency.",
      }));
      return;
    }
    if (parseAmount(amount) > Number(source.availableBalance)) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: "The selected source does not have enough available balance.",
      }));
      return;
    }

    setPayingLoanId(loan.id);
    setEarlyRepaymentErrors((current) => {
      const next = { ...current };
      delete next[loan.id];
      return next;
    });
    setEarlyRepaymentMessages((current) => {
      const next = { ...current };
      delete next[loan.id];
      return next;
    });

    try {
      const result = await apiRequest<EarlyRepaymentPaymentResult>(`/credit/loans/${loan.id}/early-repayment`, {
        method: "POST",
        token: accessToken,
        body: {
          ...(source.walletId ? { source_wallet_id: source.walletId } : {}),
          source_card_id: source.cardId,
          amount,
        },
      });
      setEarlyRepaymentResults((current) => ({
        ...current,
        [loan.id]: result,
      }));
      setLoans((current) =>
        current.map((item) =>
          item.id === loan.id
            ? {
                ...item,
                outstanding_principal: result.new_outstanding_principal,
                status: result.loan_status,
                closed_at: result.loan_status === "PAID" || result.loan_status === "CLOSED" ? new Date().toISOString() : item.closed_at,
              }
            : item,
        ),
      );
      setWallets((current) =>
        current.map((wallet) =>
          source.walletId && wallet.id === source.walletId
            ? {
                ...wallet,
                available_balance: (Number(wallet.available_balance) - Number(result.applied_extra_payment_amount)).toFixed(2),
              }
            : wallet,
        ),
      );
      const [freshLoans, freshWallets, freshCards] = await Promise.all([
        apiRequest<Loan[]>("/credit/loans", { token: accessToken }),
        apiRequest<Wallet[]>("/wallets", { token: accessToken }),
        apiRequest<Card[]>("/cards", { token: accessToken }),
      ]);
      setLoans(
        freshLoans.map((item) =>
          item.id === loan.id
            ? {
                ...item,
                outstanding_principal: result.new_outstanding_principal,
                status: result.loan_status,
                closed_at: result.loan_status === "PAID" || result.loan_status === "CLOSED" ? item.closed_at ?? new Date().toISOString() : item.closed_at,
              }
            : item,
        ),
      );
      setLoanInstallmentsByLoanId((current) => {
        const next = { ...current };
        delete next[loan.id];
        return next;
      });
      setWallets(freshWallets);
      setCards(freshCards);
      setEarlyRepaymentMessages((current) => ({
        ...current,
        [loan.id]: `${formatMoney(result.applied_extra_payment_amount, result.currency)} paid from ${source.label}.`,
      }));
      setEarlyRepaymentAmounts((current) => ({
        ...current,
        [loan.id]: "",
      }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: err instanceof ApiError ? err.message : "Could not make early repayment.",
      }));
    } finally {
      setPayingLoanId(null);
    }
  }

  async function recalculateScore() {
    if (!accessToken || isSaving) return;
    if (supportingDocuments.length === 0) {
      setError("Upload salary/income and debt documentation before submitting the score for review.");
      return;
    }
    setIsSaving(true);
    setError(null);
    setDocumentMessage(null);
    try {
      await apiRequest<CreditScore>("/credit/score/recalculate", {
        method: "POST",
        token: accessToken,
        body: {
          income: income || null,
          existing_debt: existingDebt || null,
          currency: profileCurrency,
        },
      });
      const uploadedDocuments = await uploadCreditDocuments(
        supportingDocuments,
        "CREDIT_SCORE",
        null,
        "Income and debt documentation",
      );
      const profileResponse = await apiRequest<CreditProfile>("/credit/profile", { token: accessToken });
      const documentsResponse = await apiRequest<CreditDocument[]>("/credit/documents", { token: accessToken });
      setCreditDocuments(documentsResponse);
      setProfile(profileResponse);
      setIncome(profileResponse.income);
      setExistingDebt(existingLoanDebtDisplay);
      setProfileCurrency(profileResponse.currency);
      if (uploadedDocuments.length > 0) {
        setSupportingDocuments([]);
        setDocumentMessage("Credit score submitted for admin evaluation. The score will appear after approval.");
      }
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
    if (!accessToken || !canSubmitApplication) return;
    setIsApplying(true);
    setError(null);
    setLoanPrompt(null);
    try {
      const documents = await Promise.all(
        loanApplicationDocuments.map(async (file) => ({
          document_type: `${formatProductType(loanProductType)} documentation`,
          file_name: file.name,
          content_type: file.type || null,
          file_size: file.size,
          content_base64: await readFileAsBase64(file),
        })),
      );
      const application = await apiRequest<CreditApplication>("/credit/applications", {
        method: "POST",
        token: accessToken,
        body: {
          type: "PERSONAL_LOAN",
          loan_product_type: loanProductType,
          requested_amount: principalAmountForApplication,
          currency: requestedCurrency,
          requested_term_months: Number(requestedTermMonths),
          documents,
        },
      });
      setApplications((current) => [application, ...current]);
      setLoanPrompt("Application submitted for admin review. Once approved, you can activate the loan here.");
      setDocumentMessage(`${documents.length} loan document${documents.length === 1 ? "" : "s"} attached for admin review.`);
      setLoanApplicationDocuments([]);
      setRequestedAmount("");
      setAssetPrice("");
      setDownPayment("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not create loan application.");
    } finally {
      setIsApplying(false);
    }
  }

  async function uploadCreditDocuments(
    files: File[],
    purpose: CreditDocumentPurpose,
    applicationId: string | null,
    documentType: string,
  ) {
    if (!accessToken || files.length === 0) return [];

    const uploads = await Promise.all(
      files.map(async (file) =>
        apiRequest<CreditDocument>("/credit/documents", {
          method: "POST",
          token: accessToken,
          body: {
            application_id: applicationId,
            purpose,
            document_type: documentType,
            file_name: file.name,
            content_type: file.type || null,
            file_size: file.size,
            content_base64: await readFileAsBase64(file),
          },
        }),
      ),
    );
    return uploads;
  }

  async function uploadMoreInfoDocuments(application: CreditApplication) {
    if (!accessToken || uploadingMoreInfoApplicationId) return;
    const files = additionalLoanDocuments[application.id] ?? [];
    if (files.length === 0) {
      setError("Select documents before uploading more information.");
      return;
    }

    setUploadingMoreInfoApplicationId(application.id);
    setError(null);
    setDocumentMessage(null);
    try {
      const uploadedDocuments = await uploadCreditDocuments(
        files,
        "LOAN_APPLICATION",
        application.id,
        `${formatProductType(application.loan_product_type)} additional documentation`,
      );
      const [documentsResponse, applicationsResponse] = await Promise.all([
        apiRequest<CreditDocument[]>("/credit/documents", { token: accessToken }),
        apiRequest<CreditApplication[]>("/credit/applications", { token: accessToken }),
      ]);
      setCreditDocuments(documentsResponse);
      setApplications(applicationsResponse);
      setAdditionalLoanDocuments((current) => ({ ...current, [application.id]: [] }));
      setDocumentMessage(
        `${uploadedDocuments.length} additional document${uploadedDocuments.length === 1 ? "" : "s"} uploaded for admin review.`,
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not upload additional documents.");
    } finally {
      setUploadingMoreInfoApplicationId(null);
    }
  }

  async function activateLoan(application: CreditApplication) {
    if (!accessToken || activatingApplicationId) return;
    setActivatingApplicationId(application.id);
    setError(null);
    setLoanPrompt(null);
    try {
      const loan = await apiRequest<Loan>(`/credit/applications/${application.id}/loan`, {
        method: "POST",
        token: accessToken,
      });
      setLoans((current) => [loan, ...current]);
      setWallets((current) =>
        current.map((wallet) =>
          wallet.currency === loan.currency
            ? {
                ...wallet,
                available_balance: (Number(wallet.available_balance) + Number(loan.principal_amount)).toFixed(2),
              }
            : wallet,
        ),
      );
      setLoanPrompt(`${formatMoney(loan.principal_amount, loan.currency)} was wired to your ${loan.currency} account.`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setLoanPrompt(err instanceof ApiError ? err.message : "Create a matching currency account before activating this loan.");
    } finally {
      setActivatingApplicationId(null);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Credit score</span>
          {visibleScore && <span className={bandClass(visibleScore.band)}>{visibleScore.band}</span>}
          {!visibleScore && hasPendingScoreReview && <span className="tag tag--neutral">Pending admin review</span>}
        </div>

        {isLoading && <div className="card-empty">Loading credit score...</div>}
        {!isLoading && visibleScore && (
          <div className="credit-score-layout">
            <div>
              <div className="credit-score-ring" style={{ "--score-percent": `${scorePercent}%` } as CSSProperties}>
                <div>
                  <span>{visibleScore.score}</span>
                  <small>/ 850</small>
                </div>
              </div>
            </div>
            <div className="credit-factor-grid">
              {Object.entries(visibleScore.reason_data).map(([key, value]) => (
                <div className="credit-factor" key={key}>
                  <div className="eyebrow">{formatFactorLabel(key)}</div>
                  <div className="card-panel__value">{value}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {!isLoading && !visibleScore && (
          <div className="card-empty">
            {hasPendingScoreReview
              ? "Your documents are waiting for admin evaluation."
              : "Submit the calculator and supporting documents to receive a reviewed credit score."}
          </div>
        )}
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
        {loanPrompt && <p className="credit-document-message">{loanPrompt}</p>}
        {loadWarning && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{loadWarning}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Credit score calculator</span>
        </div>
        <div className="credit-profile-inputs">
          <div className="credit-form-grid">
            <label>
              Monthly income
              <input value={income} onChange={(event) => setIncome(event.target.value)} inputMode="decimal" />
            </label>
            <label>
              Existing loan debt
              <input value={existingDebt} readOnly inputMode="decimal" />
            </label>
            <label>
              Currency
              <select value={profileCurrency} onChange={(event) => setProfileCurrency(event.target.value)}>
                {CREDIT_CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="income-document-row">
            <div className="income-document-upload">
              <span className="eyebrow">Supporting documents</span>
              <div className="income-document-upload__surface">
                <div>
                  <strong>
                    {supportingDocuments.length > 0
                      ? supportingDocuments.map((document) => document.name).join(", ")
                      : "Salary/income and debt documentation"}
                  </strong>
                  <span>
                    {supportingDocuments.length > 0
                      ? `${supportingDocuments.length} document${supportingDocuments.length === 1 ? "" : "s"} selected`
                      : "Upload salary proof plus loan, card or repayment statements"}
                  </span>
                </div>
                <label className="button--ghost income-document-upload__button">
                  Upload
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.png,.jpg,.jpeg"
                    onChange={(event) => setSupportingDocuments(Array.from(event.target.files ?? []))}
                  />
                </label>
              </div>
            </div>
            <button type="button" onClick={recalculateScore} disabled={isSaving}>
              {isSaving ? "Calculating..." : "Calculate score"}
            </button>
          </div>
        </div>
        {profile && (
          <div className="credit-profile-meta">
            <span>Profile currency</span>
            <strong>{profile.currency}</strong>
            <span>Last updated</span>
            <strong>{new Date(profile.updated_at).toLocaleString()}</strong>
          </div>
        )}
        {documentMessage && <p className="credit-document-message">{documentMessage}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Loan applications</span>
          {isCreditDetailsLoading && <span className="tag tag--neutral">Loading current loans</span>}
        </div>
        <div className="loan-application-workspace">
          <div className="credit-application-form">
            <label>
              Loan type
              <select
                value={loanProductType}
                onChange={(event) => setLoanProductType(event.target.value as LoanProductType)}
              >
                {loanProducts.map((product) => (
                  <option key={product.product_type} value={product.product_type}>
                    {product.name}
                  </option>
                ))}
              </select>
            </label>
            {supportsDownPayment ? (
              <>
                <label>
                  Asset price
                  <input
                    value={assetPrice}
                    onChange={(event) => setAssetPrice(event.target.value)}
                    inputMode="decimal"
                    placeholder="0.00"
                  />
                </label>
                <label>
                  Down payment
                  <input
                    value={downPayment}
                    onChange={(event) => setDownPayment(event.target.value)}
                    inputMode="decimal"
                    placeholder="0.00"
                  />
                </label>
              </>
            ) : (
              <label>
                Requested amount
                <input
                  value={requestedAmount}
                  onChange={(event) => setRequestedAmount(event.target.value)}
                  inputMode="decimal"
                  placeholder="0.00"
                />
              </label>
            )}
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
            <label>
              Term months
              <input
                value={requestedTermMonths}
                onChange={(event) => setRequestedTermMonths(event.target.value)}
                inputMode="numeric"
              />
            </label>
            {supportsDownPayment && (
              <div className="down-payment-breakdown">
                <div>
                  <span>Asset price</span>
                  <strong>{formatMoney(assetPriceAmount.toFixed(2), requestedCurrency)}</strong>
                </div>
                <div>
                  <span>Down payment</span>
                  <strong>{formatMoney(downPaymentAmount.toFixed(2), requestedCurrency)}</strong>
                </div>
                <div>
                  <span>Financed amount</span>
                  <strong>{formatMoney(principalAmountForApplication || "0", requestedCurrency)}</strong>
                </div>
                {hasDownPaymentError && (
                  <p>Down payment cannot be higher than the asset price.</p>
                )}
              </div>
            )}
            <div className="loan-application-documents">
              <div className="income-document-upload">
                <span className="eyebrow">Required documents</span>
                <div className="income-document-upload__surface">
                  <div>
                    <strong>
                      {loanApplicationDocuments.length > 0
                        ? loanApplicationDocuments.map((document) => document.name).join(", ")
                        : selectedLoanProduct?.required_documents.slice(0, 3).join(", ") ?? "Loan documents"}
                    </strong>
                    <span>
                      {loanApplicationDocuments.length > 0
                        ? `${loanApplicationDocuments.length} document${loanApplicationDocuments.length === 1 ? "" : "s"} selected`
                        : "Upload income, debt or asset proof before submitting"}
                    </span>
                  </div>
                  <label className="button--ghost income-document-upload__button">
                    Upload
                    <input
                      type="file"
                      multiple
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={(event) => setLoanApplicationDocuments(Array.from(event.target.files ?? []))}
                    />
                  </label>
                </div>
              </div>
            </div>
            <button type="button" onClick={createApplication} disabled={!canSubmitApplication}>
              {isApplying ? "Submitting..." : loanApplicationDocuments.length > 0 ? "Submit application" : "Upload documents to submit"}
            </button>
          </div>

          <aside className="loan-estimate-card">
            <div className="loan-estimate-card__top">
              <span className="eyebrow">Estimated monthly</span>
              <span className="tag tag--neutral">{selectedLoanProduct?.representative_apr ?? "0.00"}% APR</span>
            </div>
            {applicationEstimate ? (
              <>
                <strong>{formatMoney(applicationEstimate.monthly_payment, applicationEstimate.currency)}</strong>
                <div className="loan-estimate-card__figures">
                  <div>
                    <span>Total repayment</span>
                    <strong>{formatMoney(applicationEstimate.total_payment, applicationEstimate.currency)}</strong>
                  </div>
                  <div>
                    <span>Total interest</span>
                    <strong>{formatMoney(applicationEstimate.total_interest, applicationEstimate.currency)}</strong>
                  </div>
                </div>
                <div className="loan-estimate-card__schedule">
                  {applicationEstimate.schedule.slice(0, 3).map((installment) => (
                    <div key={installment.installment_number}>
                      <span>Month {installment.installment_number}</span>
                      <strong>{formatMoney(installment.payment_amount, applicationEstimate.currency)}</strong>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="loan-estimate-card__empty">
                {isEstimatingApplication ? "Preparing backend estimate..." : "Enter amount and term to preview payments."}
              </div>
            )}
          </aside>
        </div>

        {selectedLoanProduct && (
          <section
            className={`loan-product-panel${isLoanInfoExpanded ? "" : " loan-product-panel--collapsed"}`}
            id="loan-product-details"
          >
            <div className="loan-product-panel__summary">
              <div className="loan-product-panel__heading">
                <div>
                  <span className="eyebrow">{LOAN_PRODUCT_CONTEXT[selectedLoanProduct.product_type].accent}</span>
                  <h3>{selectedLoanProduct.name}</h3>
                  <p>{selectedLoanProduct.description}</p>
                </div>
                <button
                  type="button"
                  className="button--ghost loan-product-toggle"
                  onClick={() => setIsLoanInfoExpanded((current) => !current)}
                  aria-expanded={isLoanInfoExpanded}
                  aria-controls="loan-product-details"
                >
                  {isLoanInfoExpanded ? "Retract" : "Show details"}
                </button>
              </div>
              {isLoanInfoExpanded && (
                <div className="loan-product-panel__badges">
                  <span className="tag tag--neutral">
                    {selectedLoanProduct.collateral_required ? "Collateral" : "No collateral"}
                  </span>
                  <span className="tag tag--neutral">
                    {selectedLoanProduct.insurance_required ? "Insurance required" : "Insurance optional"}
                  </span>
                </div>
              )}
              <dl className="loan-product-metrics">
                <div>
                  <dt>Representative APR</dt>
                  <dd>{Number(selectedLoanProduct.representative_apr).toFixed(2)}%</dd>
                </div>
                <div>
                  <dt>Typical term</dt>
                  <dd>{selectedLoanProduct.typical_term_months}</dd>
                </div>
              </dl>
            </div>

            {isLoanInfoExpanded && (
              <div className="loan-product-panel__content" id="loan-product-details-content">
                <div className="loan-product-callouts">
                  <div>
                    <span className="eyebrow">Best fit</span>
                    <p>{LOAN_PRODUCT_CONTEXT[selectedLoanProduct.product_type].focus}</p>
                  </div>
                  <div>
                    <span className="eyebrow">Main liability</span>
                    <p>{LOAN_PRODUCT_CONTEXT[selectedLoanProduct.product_type].risk}</p>
                  </div>
                  <div>
                    <span className="eyebrow">Rate basis</span>
                    <p>{selectedLoanProduct.borrowing_rate_note}</p>
                  </div>
                </div>

                <div className="loan-disclosure-list">
                  <section>
                    <span className="eyebrow">Costs</span>
                    <ListPreview items={selectedLoanProduct.fees} />
                  </section>
                  <section>
                    <span className="eyebrow">Borrower duties</span>
                    <ListPreview items={selectedLoanProduct.obligations} />
                  </section>
                  <section>
                    <span className="eyebrow">Default consequences</span>
                    <ListPreview items={selectedLoanProduct.liabilities} />
                  </section>
                  <section>
                    <span className="eyebrow">Expected documents</span>
                    <ListPreview items={selectedLoanProduct.required_documents} />
                  </section>
                </div>
              </div>
            )}
          </section>
        )}

        {isCreditDetailsLoading && activeLoanApplications.length === 0 && (
          <div className="card-empty">Loading current loans...</div>
        )}

        {activeLoanApplications.length > 0 && (
          <div className="approved-offers">
            <div className="approved-offers__header">
              <div>
                <span className="eyebrow">Active / pending loans</span>
                <strong>
                  {activeLoanApplications.length} loan request{activeLoanApplications.length === 1 ? "" : "s"}
                </strong>
              </div>
              <button
                type="button"
                className="button--ghost approved-offers__toggle"
                onClick={() => setAreApprovedOffersExpanded((current) => !current)}
                aria-expanded={areApprovedOffersExpanded}
                aria-controls="approved-offers-list"
              >
                {areApprovedOffersExpanded ? "Retract" : "Show more"}
              </button>
            </div>
            {areApprovedOffersExpanded && (
              <div className="approved-offers__list" id="approved-offers-list">
                {activeLoanApplications.map((application) => {
                  const existingLoan = loans.find((loan) => loan.application_id === application.id);
                  const activeLoan = existingLoan?.status === "ACTIVE" ? existingLoan : null;
                  const breakdown = applicationBreakdowns[application.id];
                  const isApproved = application.status === "APPROVED";
                  const applicationDocuments = documentsByApplication[application.id] ?? application.documents ?? [];
                  const needsMoreInfoDocuments = applicationDocuments.filter((document) => document.status === "NEEDS_MORE_INFO");
                  const hasUploadedFollowUpDocuments =
                    needsMoreInfoDocuments.length > 0 && applicationDocuments.some((document) => document.status === "UPLOADED");
                  const needsMoreInfo = !isApproved && needsMoreInfoDocuments.length > 0 && !hasUploadedFollowUpDocuments;
                  const selectedAdditionalDocuments = additionalLoanDocuments[application.id] ?? [];
                  const canActivate = areLoansLoaded && application.type === "PERSONAL_LOAN" && isApproved && !existingLoan;
                  const isOfferExpanded = expandedOfferIds.has(application.id);
                  const isPaymentPlanExpanded = expandedPaymentPlanIds.has(application.id);
                  const breakdownId = `approved-offer-breakdown-${application.id}`;
                  const paymentPlanId = `payment-plan-${application.id}`;
                  const loanStatusLabel =
                    existingLoan?.status === "ACTIVE"
                      ? "Loan active"
                      : existingLoan?.status === "PAID" || existingLoan?.status === "CLOSED"
                        ? "Loan closed"
                        : existingLoan
                          ? existingLoan.status.toLowerCase()
                          : "";
                  const earlyRepaymentAmount = activeLoan ? earlyRepaymentAmounts[activeLoan.id] ?? "" : "";
                  const earlyRepaymentError = activeLoan ? earlyRepaymentErrors[activeLoan.id] : null;
                  const earlyRepaymentMessage = activeLoan ? earlyRepaymentMessages[activeLoan.id] : null;
                  const earlyRepaymentResult = activeLoan ? earlyRepaymentResults[activeLoan.id] : null;
                  const repaymentSources = activeLoan ? loanPaymentSourceOptions(activeLoan.currency) : [];
                  const selectedRepaymentSource = activeLoan
                    ? earlyRepaymentSourceIds[activeLoan.id] || repaymentSources[0]?.value || ""
                    : "";
                  const selectedRepaymentSourceDetails = repaymentSources.find((source) => source.value === selectedRepaymentSource);
                  const autopaySources = activeLoan ? loanAutopaySourceOptions(activeLoan.currency) : [];
                  const selectedAutopaySource = activeLoan
                    ? autopaySourceIds[activeLoan.id] || loanAutopaySourceValue(activeLoan) || autopaySources[0]?.value || ""
                    : "";
                  const selectedAutopayDate = activeLoan ? autopayDates[activeLoan.id] || loanAutopayDateValue(activeLoan) : "";
                  const isAutopayConfigOpen = activeLoan ? configuringAutopayLoanIds.has(activeLoan.id) : false;
                  const loanPaidPrincipal = activeLoan
                    ? Math.max(0, Number(activeLoan.principal_amount) - Number(activeLoan.outstanding_principal))
                    : 0;
                  const loanPaidPercent = activeLoan
                    ? Math.min(100, Math.max(0, (loanPaidPrincipal / Math.max(Number(activeLoan.principal_amount), 1)) * 100))
                    : 0;
                  const realInstallments = activeLoan ? loanInstallmentsByLoanId[activeLoan.id] : undefined;
                  const calculatedPaymentPlanRows =
                    breakdown?.schedule.map((installment) => ({
                      number: installment.installment_number,
                      dueDate: null,
                      paymentAmount: installment.payment_amount,
                      principalAmount: installment.principal_amount,
                      interestAmount: installment.interest_amount,
                      remainingPrincipal: installment.remaining_principal,
                      status: null,
                    })) ?? [];
                  const paymentPlanRows = realInstallments && realInstallments.length > 0
                    ? realInstallments.map((installment) => ({
                        number: installment.installment_number,
                        dueDate: installment.due_date,
                        paymentAmount: installment.payment_amount,
                        principalAmount: installment.principal_amount,
                        interestAmount: installment.interest_amount,
                        remainingPrincipal: installment.remaining_principal,
                        status: installment.status,
                      }))
                    : calculatedPaymentPlanRows;
                  const paymentPlanError = paymentPlanErrors[application.id];
                  return (
                    <article
                      className={`approved-offer-card${isOfferExpanded ? "" : " approved-offer-card--collapsed"}`}
                      key={application.id}
                    >
                      <div className="approved-offer-card__summary">
                        <div>
                          <span className="eyebrow">{formatProductType(application.loan_product_type)}</span>
                          <h3>{formatMoney(application.offered_amount ?? application.requested_amount, application.currency)}</h3>
                          <p>
                            {isApproved
                              ? `Approved on ${application.resolved_at ? new Date(application.resolved_at).toLocaleDateString() : "review"}`
                              : `Submitted on ${new Date(application.created_at).toLocaleDateString()}`}
                          </p>
                        </div>
                        <div className="approved-offer-card__actions">
                          <span className={isApproved ? "tag tag--accent" : "tag tag--neutral"}>
                            {isApproved
                              ? "Approved"
                              : needsMoreInfo
                                ? "More info needed"
                                : hasUploadedFollowUpDocuments
                                  ? "Documents submitted"
                                  : "Pending review"}
                          </span>
                          {existingLoan ? (
                            <span className={activeLoan ? "tag tag--accent" : "tag tag--neutral"}>{loanStatusLabel}</span>
                          ) : isApproved ? (
                            <button
                              type="button"
                              className="button--ghost"
                              onClick={() => activateLoan(application)}
                              disabled={!canActivate || activatingApplicationId === application.id}
                            >
                              {activatingApplicationId === application.id ? "Activating..." : "Activate loan"}
                            </button>
                          ) : null}
                        </div>
                      </div>

                      {!isApproved ? (
                        <div className="approved-offer-card__main-payment">
                          <span className="eyebrow">Review status</span>
                          <strong>
                            {needsMoreInfo ? "More documents needed" : hasUploadedFollowUpDocuments ? "Additional docs submitted" : "Pending"}
                          </strong>
                          <span>
                            {needsMoreInfo
                              ? "Admin needs extra documentation before deciding this loan application."
                              : hasUploadedFollowUpDocuments
                                ? "Your additional documents are waiting for admin review."
                              : "Admin review will decide the final offer, rate and repayment schedule."}
                          </span>
                        </div>
                      ) : breakdown ? (
                        <>
                          <div className="approved-offer-card__main-payment">
                            <span className="eyebrow">Monthly payment</span>
                            <strong>{formatMoney(breakdown.monthly_payment, breakdown.currency)}</strong>
                            <span>
                              {application.offered_interest_rate ?? breakdown.annual_interest_rate}% APR / {breakdown.term_months} months
                            </span>
                            <button
                              type="button"
                              className="button--ghost approved-offer-card__toggle"
                              onClick={() => toggleApprovedOfferDetails(application.id)}
                              aria-expanded={isOfferExpanded}
                              aria-controls={breakdownId}
                            >
                              {isOfferExpanded ? "Retract" : "Show details"}
                            </button>
                            <button
                              type="button"
                              className="button--ghost approved-offer-card__toggle"
                              onClick={() => void togglePaymentPlan(application.id, activeLoan ?? undefined)}
                              aria-expanded={isPaymentPlanExpanded}
                              aria-controls={paymentPlanId}
                              disabled={loadingPaymentPlanLoanId === activeLoan?.id}
                            >
                              {loadingPaymentPlanLoanId === activeLoan?.id
                                ? "Loading plan..."
                                : isPaymentPlanExpanded
                                  ? "Retract plan"
                                  : "Payment plan"}
                            </button>
                          </div>
                          {isOfferExpanded && (
                            <div className="approved-offer-card__details" id={breakdownId}>
                              <div className="approved-offer-card__figures">
                                <div>
                                  <span className="eyebrow">Annual rate</span>
                                  <strong>{application.offered_interest_rate ?? breakdown.annual_interest_rate}%</strong>
                                </div>
                                <div>
                                  <span className="eyebrow">Term</span>
                                  <strong>{breakdown.term_months} months</strong>
                                </div>
                                <div>
                                  <span className="eyebrow">Total interest</span>
                                  <strong>{formatMoney(breakdown.total_interest, breakdown.currency)}</strong>
                                </div>
                                <div>
                                  <span className="eyebrow">Total repayment</span>
                                  <strong>{formatMoney(breakdown.total_payment, breakdown.currency)}</strong>
                                </div>
                              </div>
                            </div>
                          )}
                          {isPaymentPlanExpanded && (
                            <div className="loan-payment-plan" id={paymentPlanId}>
                              <div className="loan-payment-plan__header">
                                <div>
                                  <span className="eyebrow">Payment plan</span>
                                  <strong>{paymentPlanRows.length || breakdown.term_months} monthly payments</strong>
                                </div>
                                <div className="loan-payment-plan__actions">
                                  <span className="tag tag--neutral">{breakdown.term_months} months</span>
                                  <button
                                    type="button"
                                    className="button--ghost loan-payment-plan__download"
                                    onClick={() => downloadPaymentPlan(application, breakdown, paymentPlanRows)}
                                    disabled={paymentPlanRows.length === 0}
                                  >
                                    <Download size={16} aria-hidden="true" />
                                    Download Excel
                                  </button>
                                </div>
                              </div>
                              {paymentPlanError ? (
                                <p className="early-repayment-card__error">{paymentPlanError}</p>
                              ) : paymentPlanRows.length === 0 ? (
                                <p className="approved-offer-card__loading">Preparing payment plan...</p>
                              ) : (
                                <div className="loan-payment-plan__rows">
                                  {paymentPlanRows.map((installment) => (
                                    <div className="loan-payment-plan__row" key={installment.number}>
                                      <span>
                                        #{installment.number}
                                        {installment.dueDate ? ` - ${new Date(installment.dueDate).toLocaleDateString()}` : ""}
                                      </span>
                                      <strong>{formatMoney(installment.paymentAmount, breakdown.currency)}</strong>
                                      <small>
                                        Principal {formatMoney(installment.principalAmount, breakdown.currency)} / Interest{" "}
                                        {formatMoney(installment.interestAmount, breakdown.currency)}
                                      </small>
                                      <small>{formatMoney(installment.remainingPrincipal, breakdown.currency)} remaining</small>
                                      {installment.status && <span className="tag tag--outline">{installment.status}</span>}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                          {activeLoan && (
                            <div className="early-repayment-card">
                              <div className="early-repayment-card__top">
                                <div>
                                  <span className="eyebrow">Early repayment</span>
                                  <strong>Simulate or make an extra principal payment</strong>
                                </div>
                                <span className="tag tag--neutral">
                                  {formatMoney(activeLoan.outstanding_principal, activeLoan.currency)} left
                                </span>
                              </div>
                              {!isAutopayConfigOpen && (
                                <>
                                  <div className="early-repayment-card__form">
                                    <label>
                                      Amount
                                      <input
                                        type="number"
                                        min="0"
                                        step="0.01"
                                        value={earlyRepaymentAmount}
                                        onChange={(event) =>
                                          setEarlyRepaymentAmounts((current) => ({
                                            ...current,
                                            [activeLoan.id]: event.target.value,
                                          }))
                                        }
                                        placeholder={`0.00 ${activeLoan.currency}`}
                                      />
                                    </label>
                                    <label>
                                      Pay from
                                      <select
                                        value={selectedRepaymentSource}
                                        onChange={(event) =>
                                          setEarlyRepaymentSourceIds((current) => ({
                                            ...current,
                                            [activeLoan.id]: event.target.value,
                                          }))
                                        }
                                        disabled={repaymentSources.length === 0}
                                      >
                                        {repaymentSources.length === 0 ? (
                                          <option value="">No source available</option>
                                        ) : (
                                          repaymentSources.map((source) => (
                                            <option key={source.value} value={source.value}>
                                              {source.label}
                                            </option>
                                          ))
                                        )}
                                      </select>
                                    </label>
                                    <button
                                      type="button"
                                      className="button--ghost early-repayment-card__simulate"
                                      onClick={() => simulateEarlyRepayment(activeLoan)}
                                      disabled={simulatingLoanId === activeLoan.id}
                                    >
                                      {simulatingLoanId === activeLoan.id ? "Simulating..." : "Simulate"}
                                    </button>
                                <button
                                  type="button"
                                  className="credit-card-payment__submit"
                                      onClick={() => makeEarlyRepayment(activeLoan, repaymentSources)}
                                      disabled={payingLoanId === activeLoan.id || repaymentSources.length === 0}
                                    >
                                      {payingLoanId === activeLoan.id ? "Paying..." : "Make payment"}
                                    </button>
                                  </div>
                                  {selectedRepaymentSource && (
                                    <p className="early-repayment-card__source-balance">
                                      Available{" "}
                                      {selectedRepaymentSourceDetails
                                        ? `${Number(selectedRepaymentSourceDetails.availableBalance).toLocaleString(undefined, {
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2,
                                          })} ${activeLoan.currency}`
                                        : `0.00 ${activeLoan.currency}`}
                                    </p>
                                  )}
                                </>
                              )}
                              <div className="loan-payment-progress">
                                <div className="loan-payment-progress__top">
                                  <span>Loan paid</span>
                                  <strong>{loanPaidPercent.toFixed(0)}%</strong>
                                </div>
                                <div className="loan-payment-progress__track" aria-hidden="true">
                                  <span style={{ width: `${loanPaidPercent}%` }} />
                                </div>
                                <div className="loan-payment-progress__figures">
                                  <span>{formatMoney(loanPaidPrincipal.toFixed(2), activeLoan.currency)} paid</span>
                                  <span>{formatMoney(activeLoan.outstanding_principal, activeLoan.currency)} remaining</span>
                                </div>
                              </div>
                              <div className="early-repayment-card__top">
                                {activeLoan.autopay_enabled && (
                                  <div>
                                    <span className="eyebrow">Recurring payment</span>
                                    <strong>
                                      Set for {new Date(activeLoan.autopay_next_run_on || activeLoan.next_payment_date).toLocaleDateString()}
                                    </strong>
                                  </div>
                                )}
                                <div className="approved-offer-card__actions">
                                  {activeLoan.autopay_enabled ? (
                                    <>
                                      <button
                                        type="button"
                                        className="button--ghost"
                                        onClick={() => updateLoanAutopay(activeLoan, autopaySources, false)}
                                        disabled={updatingAutopayLoanId === activeLoan.id}
                                      >
                                        {updatingAutopayLoanId === activeLoan.id ? "Saving..." : "Disable recurring"}
                                      </button>
                                      <button type="button" className="button--ghost" onClick={() => openAutopayConfig(activeLoan)}>
                                        Change schedule
                                      </button>
                                    </>
                                  ) : (
                                    <button type="button" className="button--ghost" onClick={() => openAutopayConfig(activeLoan)}>
                                      Set up recurring
                                    </button>
                                  )}
                                </div>
                              </div>
                              {isAutopayConfigOpen && (
                                <div className="early-repayment-card__form">
                                  <label>
                                    Pay from
                                    <select
                                      value={selectedAutopaySource}
                                      onChange={(event) =>
                                        setAutopaySourceIds((current) => ({
                                          ...current,
                                          [activeLoan.id]: event.target.value,
                                        }))
                                      }
                                      disabled={autopaySources.length === 0}
                                    >
                                      {autopaySources.length === 0 ? (
                                        <option value="">No account or debit card available</option>
                                      ) : (
                                        autopaySources.map((source) => (
                                          <option key={source.value} value={source.value}>
                                            {source.label}
                                          </option>
                                        ))
                                      )}
                                    </select>
                                  </label>
                                  <label>
                                    Amount
                                    <input
                                      type="number"
                                      min={activeLoan.monthly_payment}
                                      step="0.01"
                                      value={autopayAmounts[activeLoan.id] || loanAutopayAmountValue(activeLoan)}
                                      onChange={(event) =>
                                        setAutopayAmounts((current) => ({
                                          ...current,
                                          [activeLoan.id]: event.target.value,
                                        }))
                                      }
                                      placeholder={`0.00 ${activeLoan.currency}`}
                                    />
                                  </label>
                                  <label>
                                    Payment date
                                    <input
                                      type="date"
                                      min={new Date().toISOString().slice(0, 10)}
                                      value={selectedAutopayDate}
                                      onChange={(event) =>
                                        setAutopayDates((current) => ({
                                          ...current,
                                          [activeLoan.id]: event.target.value,
                                        }))
                                      }
                                    />
                                  </label>
                                  <button
                                    type="button"
                                    className="credit-card-payment__submit"
                                    onClick={() => updateLoanAutopay(activeLoan, autopaySources, true)}
                                    disabled={updatingAutopayLoanId === activeLoan.id || autopaySources.length === 0}
                                  >
                                    {updatingAutopayLoanId === activeLoan.id
                                      ? "Saving..."
                                      : activeLoan.autopay_enabled
                                        ? "Update recurring"
                                        : "Enable recurring"}
                                  </button>
                                  <button type="button" className="button--ghost early-repayment-card__simulate" onClick={() => closeAutopayConfig(activeLoan.id)}>
                                    Cancel
                                  </button>
                                </div>
                              )}
                              {earlyRepaymentError && <p className="early-repayment-card__error">{earlyRepaymentError}</p>}
                              {earlyRepaymentMessage && <p className="early-repayment-card__message">{earlyRepaymentMessage}</p>}
                              {earlyRepaymentResult && (
                                <div className="early-repayment-card__result">
                                  <div>
                                    <span>Interest saved</span>
                                    <strong>
                                      {formatMoney(earlyRepaymentResult.total_interest_saved, earlyRepaymentResult.currency)}
                                    </strong>
                                  </div>
                                  <div>
                                    <span>Shorter by</span>
                                    <strong>{earlyRepaymentResult.term_months_reduced} months</strong>
                                  </div>
                                  <div>
                                    <span>New balance</span>
                                    <strong>
                                      {formatMoney(earlyRepaymentResult.new_outstanding_principal, earlyRepaymentResult.currency)}
                                    </strong>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="approved-offer-card__loading" id={breakdownId}>
                          Preparing backend payment breakdown...
                        </div>
                      )}
                      {needsMoreInfo && (
                        <div className="loan-more-info-upload">
                          <div className="loan-more-info-upload__copy">
                            <span className="eyebrow">Requested documents</span>
                            <strong>
                              {selectedAdditionalDocuments.length > 0
                                ? selectedAdditionalDocuments.map((document) => document.name).join(", ")
                                : needsMoreInfoDocuments.map((document) => document.document_type).join(", ")}
                            </strong>
                            {needsMoreInfoDocuments.some((document) => document.review_note) && (
                              <span>{needsMoreInfoDocuments.find((document) => document.review_note)?.review_note}</span>
                            )}
                          </div>
                          <div className="loan-more-info-upload__actions">
                            <label className="button--ghost loan-more-info-upload__select">
                              Upload files
                              <input
                                type="file"
                                multiple
                                accept=".pdf,.png,.jpg,.jpeg"
                                onChange={(event) =>
                                  setAdditionalLoanDocuments((current) => ({
                                    ...current,
                                    [application.id]: Array.from(event.target.files ?? []),
                                  }))
                                }
                              />
                            </label>
                            <button
                              type="button"
                              className="credit-card-payment__submit"
                              onClick={() => uploadMoreInfoDocuments(application)}
                              disabled={uploadingMoreInfoApplicationId === application.id || selectedAdditionalDocuments.length === 0}
                            >
                              {uploadingMoreInfoApplicationId === application.id ? "Uploading..." : "Send documents"}
                            </button>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {closedLoanApplications.length > 0 && (
          <div className="approved-offers">
            <div className="approved-offers__header">
              <div>
                <span className="eyebrow">Past loans</span>
                <strong>
                  {closedLoanApplications.length} closed loan{closedLoanApplications.length === 1 ? "" : "s"}
                </strong>
              </div>
              <button
                type="button"
                className="button--ghost approved-offers__toggle"
                onClick={() => setArePastLoansExpanded((current) => !current)}
                aria-expanded={arePastLoansExpanded}
                aria-controls="past-loans-list"
              >
                {arePastLoansExpanded ? "Retract" : "Show more"}
              </button>
            </div>
            {arePastLoansExpanded && (
              <div className="approved-offers__list" id="past-loans-list">
                {closedLoanApplications.map((application) => {
                  const closedLoan = loans.find((loan) => loan.application_id === application.id);
                  const breakdown = applicationBreakdowns[application.id];
                  return (
                    <article className="approved-offer-card approved-offer-card--collapsed" key={application.id}>
                      <div className="approved-offer-card__summary">
                        <div>
                          <span className="eyebrow">{formatProductType(application.loan_product_type)}</span>
                          <h3>{formatMoney(application.offered_amount ?? application.requested_amount, application.currency)}</h3>
                          <p>
                            Closed {closedLoan?.closed_at ? new Date(closedLoan.closed_at).toLocaleDateString() : "after repayment"}
                          </p>
                        </div>
                        <div className="approved-offer-card__actions">
                          <span className="tag tag--neutral">Loan closed</span>
                        </div>
                      </div>
                      <div className="approved-offer-card__details">
                        <div className="approved-offer-card__figures">
                          <div>
                            <span className="eyebrow">Original principal</span>
                            <strong>{formatMoney(closedLoan?.principal_amount ?? application.offered_amount ?? application.requested_amount, application.currency)}</strong>
                          </div>
                          <div>
                            <span className="eyebrow">Outstanding</span>
                            <strong>{formatMoney(closedLoan?.outstanding_principal ?? "0.00", closedLoan?.currency ?? application.currency)}</strong>
                          </div>
                          <div>
                            <span className="eyebrow">Monthly payment</span>
                            <strong>
                              {closedLoan
                                ? formatMoney(closedLoan.monthly_payment, closedLoan.currency)
                                : breakdown
                                  ? formatMoney(breakdown.monthly_payment, breakdown.currency)
                                  : "Closed"}
                            </strong>
                          </div>
                          <div>
                            <span className="eyebrow">Term</span>
                            <strong>{closedLoan?.term_months ?? breakdown?.term_months ?? application.requested_term_months ?? 0} months</strong>
                          </div>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        )}

      </div>
    </section>
  );
}

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";
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
import { formatDecimalAmount } from "../utils";

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

function defaultLoanProducts(t: (key: string) => string): LoanProduct[] {
  return [
    {
      product_type: "PERSONAL_LOAN",
      name: t("credit.personalLoanName"),
      description: t("credit.personalLoanDescription"),
      representative_apr: "9.90",
      borrowing_rate_note: t("credit.personalLoanRateNote"),
      typical_term_months: t("credit.termMonthsRange"),
      fees: [t("credit.feeAdmin"), t("credit.feeLate"), t("credit.feeEarly")],
      obligations: [t("credit.obligationRepay"), t("credit.obligationReview")],
      liabilities: [t("credit.liabilityLate"), t("credit.liabilityCollections")],
      required_documents: [t("credit.docIdentity"), t("credit.docIncome"), t("credit.docBankHistory")],
      collateral_required: false,
      insurance_required: false,
    },
  ];
}

function loanProductContext(t: (key: string) => string): Record<LoanProductType, { focus: string; risk: string; accent: string }> {
  return {
    PERSONAL_LOAN: { focus: t("credit.personalLoanFocus"), risk: t("credit.personalLoanRisk"), accent: t("credit.personalLoanAccent") },
    MORTGAGE: { focus: t("credit.mortgageFocus"), risk: t("credit.mortgageRisk"), accent: t("credit.mortgageAccent") },
    AUTO_LOAN: { focus: t("credit.autoFocus"), risk: t("credit.autoRisk"), accent: t("credit.autoAccent") },
    STUDENT_LOAN: { focus: t("credit.studentFocus"), risk: t("credit.studentRisk"), accent: t("credit.studentAccent") },
    HOME_IMPROVEMENT: { focus: t("credit.homeImprovementFocus"), risk: t("credit.homeImprovementRisk"), accent: t("credit.homeImprovementAccent") },
    DEBT_CONSOLIDATION: { focus: t("credit.debtConsolidationFocus"), risk: t("credit.debtConsolidationRisk"), accent: t("credit.debtConsolidationAccent") },
  };
}

function bandClass(band: string): string {
  if (band === "EXCELLENT" || band === "VERY_GOOD" || band === "GOOD") return "tag tag--accent";
  if (band === "FAIR") return "tag tag--neutral";
  return "tag tag--warning";
}

const BAND_LABEL_KEY: Record<string, string> = {
  EXCELLENT: "credit.excellent",
  VERY_GOOD: "credit.veryGood",
  GOOD: "credit.good",
  FAIR: "credit.fair",
  RISKY: "credit.risky",
};

function formatBand(band: string, t: (key: string) => string): string {
  const key = BAND_LABEL_KEY[band];
  return key ? t(key) : band;
}

function formatFactorLabel(key: string): string {
  return key
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatProductType(type: LoanProductType | null, t: (key: string) => string): string {
  if (!type) return t("credit.mortgage");
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatMoney(value: string, currency = "RON"): string {
  return `${formatDecimalAmount(Number(value))} ${currency}`;
}

function escapeExcelCell(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatExcelNumber(value: string): string {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue.toFixed(2) : "0.00";
}

function readFileAsBase64(file: File, t: (key: string) => string): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error(t("credit.couldNotReadDocument")));
    reader.readAsDataURL(file);
  });
}

function parseAmount(value: string): number {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : 0;
}

function walletDisplayName(wallet: Wallet): string {
  const base = wallet.nickname ? `${wallet.currency} — ${wallet.nickname}` : wallet.currency;
  return `${base}${wallet.is_main ? " - Main" : ""}`;
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
  const { t } = useTranslation();
  const DEFAULT_LOAN_PRODUCTS = useMemo(() => defaultLoanProducts(t), [t]);
  const LOAN_PRODUCT_CONTEXT = useMemo(() => loanProductContext(t), [t]);
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
        setLoadWarning(t("credit.scoreLoadedNoApplications"));
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
        setLoadWarning(t("credit.scoreLoadedNoLoans"));
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
      setError(err instanceof ApiError ? err.message : t("credit.couldNotLoadScore"));
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
        [applicationId]: err instanceof ApiError ? err.message : t("credit.couldNotLoadPaymentPlan"),
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
    const title = t("credit.loanPaymentPlanTitle", { amount: formatMoney(amount, application.currency) });
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
          <p>${escapeExcelCell(t("credit.generated", { date: generatedAt }))}</p>
          <p>${escapeExcelCell(t("credit.apr", { rate: application.offered_interest_rate ?? breakdown.annual_interest_rate }))}</p>
          <p>${escapeExcelCell(t("credit.term", { months: breakdown.term_months }))}</p>
          <p>${escapeExcelCell(t("credit.currency", { currency: breakdown.currency }))}</p>
          <table>
            <thead>
              <tr>
                <th>${escapeExcelCell(t("credit.paymentNumber"))}</th>
                <th>${escapeExcelCell(t("credit.dueDate"))}</th>
                <th>${escapeExcelCell(t("credit.paymentAmount"))}</th>
                <th>${escapeExcelCell(t("credit.principal"))}</th>
                <th>${escapeExcelCell(t("credit.interest"))}</th>
                <th>${escapeExcelCell(t("credit.remainingPrincipal"))}</th>
                <th>${escapeExcelCell(t("credit.status"))}</th>
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
            label: wallet
              ? t("credit.debitLastFourWithWallet", { lastFour: card.last_four, wallet: walletDisplayName(wallet) })
              : t("credit.debitLastFour", { lastFour: card.last_four }),
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
          label: t("credit.accountSuffix", { wallet: walletDisplayName(wallet) }),
          currency: wallet.currency,
          availableBalance: wallet.available_balance,
        })),
      ...activeCreditCards
        .filter((card) => card.credit_account?.currency === currency)
        .map((card) => ({
          value: `CREDIT_CARD:${card.id}`,
          walletId: "",
          cardId: card.id,
          label: t("credit.creditLastFour", { lastFour: card.last_four }),
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
        [loan.id]: t("credit.noAccountOrDebit"),
      }));
      return;
    }
    if (enabled && !selectedDate) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: t("credit.chooseRecurringDate"),
      }));
      return;
    }
    if (enabled && parseAmount(selectedAmount) <= 0) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: t("credit.enterPositiveRecurring"),
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
        [loan.id]: enabled ? t("credit.recurringEnabled") : t("credit.recurringDisabled"),
      }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: err instanceof ApiError ? err.message : t("credit.couldNotUpdateRecurring"),
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
        [loan.id]: t("credit.enterPositiveExtra"),
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
        [loan.id]: err instanceof ApiError ? err.message : t("credit.couldNotSimulate"),
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
        [loan.id]: t("credit.enterPositivePayment"),
      }));
      return;
    }
    if (!source) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: t("credit.noPaymentSource"),
      }));
      return;
    }
    if (parseAmount(amount) > Number(source.availableBalance)) {
      setEarlyRepaymentErrors((current) => ({
        ...current,
        [loan.id]: t("credit.insufficientBalance"),
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
        [loan.id]: t("credit.paidFrom", { amount: formatMoney(result.applied_extra_payment_amount, result.currency), source: source.label }),
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
        [loan.id]: err instanceof ApiError ? err.message : t("credit.couldNotMakeEarlyRepayment"),
      }));
    } finally {
      setPayingLoanId(null);
    }
  }

  async function recalculateScore() {
    if (!accessToken || isSaving) return;
    if (supportingDocuments.length === 0) {
      setError(t("credit.uploadDocsBeforeScore"));
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
        t("credit.incomeDebtDocs"),
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
        setDocumentMessage(t("credit.scoreSubmitted"));
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("credit.couldNotRecalculate"));
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
          document_type: t("credit.documentation", { type: formatProductType(loanProductType, t) }),
          file_name: file.name,
          content_type: file.type || null,
          file_size: file.size,
          content_base64: await readFileAsBase64(file, t),
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
      setLoanPrompt(t("credit.applicationSubmitted"));
      setDocumentMessage(t("credit.docsAttached", { count: documents.length }));
      setLoanApplicationDocuments([]);
      setRequestedAmount("");
      setAssetPrice("");
      setDownPayment("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("credit.couldNotCreateApplication"));
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
            content_base64: await readFileAsBase64(file, t),
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
      setError(t("credit.selectDocsBeforeUpload"));
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
        t("credit.additionalDocumentation", { type: formatProductType(application.loan_product_type, t) }),
      );
      const [documentsResponse, applicationsResponse] = await Promise.all([
        apiRequest<CreditDocument[]>("/credit/documents", { token: accessToken }),
        apiRequest<CreditApplication[]>("/credit/applications", { token: accessToken }),
      ]);
      setCreditDocuments(documentsResponse);
      setApplications(applicationsResponse);
      setAdditionalLoanDocuments((current) => ({ ...current, [application.id]: [] }));
      setDocumentMessage(t("credit.docsUploaded", { count: uploadedDocuments.length }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("credit.couldNotUploadAdditional"));
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
      setLoanPrompt(t("credit.wiredToAccount", { amount: formatMoney(loan.principal_amount, loan.currency), currency: loan.currency }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setLoanPrompt(err instanceof ApiError ? err.message : t("credit.createMatchingAccount"));
    } finally {
      setActivatingApplicationId(null);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("credit.creditScore")}</span>
          {visibleScore && <span className={bandClass(visibleScore.band)}>{formatBand(visibleScore.band, t)}</span>}
          {!visibleScore && hasPendingScoreReview && <span className="tag tag--neutral">{t("credit.pendingAdminReview")}</span>}
        </div>

        {isLoading && <div className="card-empty">{t("credit.loadingScore")}</div>}
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
              ? t("credit.waitingForEvaluation")
              : t("credit.submitCalculator")}
          </div>
        )}
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
        {loanPrompt && <p className="credit-document-message">{loanPrompt}</p>}
        {loadWarning && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{loadWarning}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("credit.calculator")}</span>
        </div>
        <div className="credit-profile-inputs">
          <div className="credit-form-grid">
            <label>
              {t("credit.monthlyIncome")}
              <input value={income} onChange={(event) => setIncome(event.target.value)} inputMode="decimal" />
            </label>
            <label>
              {t("credit.existingLoanDebt")}
              <input value={existingDebt} readOnly inputMode="decimal" />
            </label>
            <label>
              {t("credit.currencyLabel")}
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
              <span className="eyebrow">{t("credit.supportingDocuments")}</span>
              <div className="income-document-upload__surface">
                <div>
                  <strong>
                    {supportingDocuments.length > 0
                      ? supportingDocuments.map((document) => document.name).join(", ")
                      : t("credit.salaryIncomeDocs")}
                  </strong>
                  <span>
                    {supportingDocuments.length > 0
                      ? t("credit.documentsSelected", { count: supportingDocuments.length })
                      : t("credit.uploadSalaryProof")}
                  </span>
                </div>
                <label className="button--ghost income-document-upload__button">
                  {t("credit.upload")}
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
              {isSaving ? t("credit.calculating") : t("credit.calculateScore")}
            </button>
          </div>
        </div>
        {profile && (
          <div className="credit-profile-meta">
            <span>{t("credit.profileCurrency")}</span>
            <strong>{profile.currency}</strong>
            <span>{t("credit.lastUpdated")}</span>
            <strong>{new Date(profile.updated_at).toLocaleString()}</strong>
          </div>
        )}
        {documentMessage && <p className="credit-document-message">{documentMessage}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("credit.loanApplications")}</span>
          {isCreditDetailsLoading && <span className="tag tag--neutral">{t("credit.loadingCurrentLoans")}</span>}
        </div>
        <div className="loan-application-workspace">
          <div className="credit-application-form">
            <label>
              {t("credit.loanType")}
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
                  {t("credit.assetPrice")}
                  <input
                    value={assetPrice}
                    onChange={(event) => setAssetPrice(event.target.value)}
                    inputMode="decimal"
                    placeholder="0.00"
                  />
                </label>
                <label>
                  {t("credit.downPayment")}
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
                {t("credit.requestedAmount")}
                <input
                  value={requestedAmount}
                  onChange={(event) => setRequestedAmount(event.target.value)}
                  inputMode="decimal"
                  placeholder="0.00"
                />
              </label>
            )}
            <label>
              {t("credit.currencyLabel")}
              <select value={requestedCurrency} onChange={(event) => setRequestedCurrency(event.target.value)}>
                {CREDIT_CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("credit.termMonths")}
              <input
                value={requestedTermMonths}
                onChange={(event) => setRequestedTermMonths(event.target.value)}
                inputMode="numeric"
              />
            </label>
            {supportsDownPayment && (
              <div className="down-payment-breakdown">
                <div>
                  <span>{t("credit.assetPrice")}</span>
                  <strong>{formatMoney(assetPriceAmount.toFixed(2), requestedCurrency)}</strong>
                </div>
                <div>
                  <span>{t("credit.downPayment")}</span>
                  <strong>{formatMoney(downPaymentAmount.toFixed(2), requestedCurrency)}</strong>
                </div>
                <div>
                  <span>{t("credit.financedAmount")}</span>
                  <strong>{formatMoney(principalAmountForApplication || "0", requestedCurrency)}</strong>
                </div>
                {hasDownPaymentError && (
                  <p>{t("credit.downPaymentTooHigh")}</p>
                )}
              </div>
            )}
            <div className="loan-application-documents">
              <div className="income-document-upload">
                <span className="eyebrow">{t("credit.requiredDocuments")}</span>
                <div className="income-document-upload__surface">
                  <div>
                    <strong>
                      {loanApplicationDocuments.length > 0
                        ? loanApplicationDocuments.map((document) => document.name).join(", ")
                        : selectedLoanProduct?.required_documents.slice(0, 3).join(", ") ?? t("credit.loanDocumentsFallback")}
                    </strong>
                    <span>
                      {loanApplicationDocuments.length > 0
                        ? t("credit.documentsSelected", { count: loanApplicationDocuments.length })
                        : t("credit.uploadIncomeProof")}
                    </span>
                  </div>
                  <label className="button--ghost income-document-upload__button">
                    {t("credit.upload")}
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
              {isApplying ? t("credit.submitting") : loanApplicationDocuments.length > 0 ? t("credit.submitApplication") : t("credit.uploadDocsToSubmit")}
            </button>
          </div>

          <aside className="loan-estimate-card">
            <div className="loan-estimate-card__top">
              <span className="eyebrow">{t("credit.estimatedMonthly")}</span>
              <span className="tag tag--neutral">{t("credit.aprSuffix", { rate: selectedLoanProduct?.representative_apr ?? "0.00" })}</span>
            </div>
            {applicationEstimate ? (
              <>
                <strong>{formatMoney(applicationEstimate.monthly_payment, applicationEstimate.currency)}</strong>
                <div className="loan-estimate-card__figures">
                  <div>
                    <span>{t("credit.totalRepayment")}</span>
                    <strong>{formatMoney(applicationEstimate.total_payment, applicationEstimate.currency)}</strong>
                  </div>
                  <div>
                    <span>{t("credit.totalInterest")}</span>
                    <strong>{formatMoney(applicationEstimate.total_interest, applicationEstimate.currency)}</strong>
                  </div>
                </div>
                <div className="loan-estimate-card__schedule">
                  {applicationEstimate.schedule.slice(0, 3).map((installment) => (
                    <div key={installment.installment_number}>
                      <span>{t("credit.month", { number: installment.installment_number })}</span>
                      <strong>{formatMoney(installment.payment_amount, applicationEstimate.currency)}</strong>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="loan-estimate-card__empty">
                {isEstimatingApplication ? t("credit.preparingEstimate") : t("credit.enterAmountAndTerm")}
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
                  {isLoanInfoExpanded ? t("credit.retract") : t("credit.showDetails")}
                </button>
              </div>
              {isLoanInfoExpanded && (
                <div className="loan-product-panel__badges">
                  <span className="tag tag--neutral">
                    {selectedLoanProduct.collateral_required ? t("credit.collateral") : t("credit.noCollateral")}
                  </span>
                  <span className="tag tag--neutral">
                    {selectedLoanProduct.insurance_required ? t("credit.insuranceRequired") : t("credit.insuranceOptional")}
                  </span>
                </div>
              )}
              <dl className="loan-product-metrics">
                <div>
                  <dt>{t("credit.representativeApr")}</dt>
                  <dd>{Number(selectedLoanProduct.representative_apr).toFixed(2)}%</dd>
                </div>
                <div>
                  <dt>{t("credit.typicalTerm")}</dt>
                  <dd>{selectedLoanProduct.typical_term_months}</dd>
                </div>
              </dl>
            </div>

            {isLoanInfoExpanded && (
              <div className="loan-product-panel__content" id="loan-product-details-content">
                <div className="loan-product-callouts">
                  <div>
                    <span className="eyebrow">{t("credit.bestFit")}</span>
                    <p>{LOAN_PRODUCT_CONTEXT[selectedLoanProduct.product_type].focus}</p>
                  </div>
                  <div>
                    <span className="eyebrow">{t("credit.mainLiability")}</span>
                    <p>{LOAN_PRODUCT_CONTEXT[selectedLoanProduct.product_type].risk}</p>
                  </div>
                  <div>
                    <span className="eyebrow">{t("credit.rateBasis")}</span>
                    <p>{selectedLoanProduct.borrowing_rate_note}</p>
                  </div>
                </div>

                <div className="loan-disclosure-list">
                  <section>
                    <span className="eyebrow">{t("credit.costs")}</span>
                    <ListPreview items={selectedLoanProduct.fees} />
                  </section>
                  <section>
                    <span className="eyebrow">{t("credit.borrowerDuties")}</span>
                    <ListPreview items={selectedLoanProduct.obligations} />
                  </section>
                  <section>
                    <span className="eyebrow">{t("credit.defaultConsequences")}</span>
                    <ListPreview items={selectedLoanProduct.liabilities} />
                  </section>
                  <section>
                    <span className="eyebrow">{t("credit.expectedDocuments")}</span>
                    <ListPreview items={selectedLoanProduct.required_documents} />
                  </section>
                </div>
              </div>
            )}
          </section>
        )}

        {isCreditDetailsLoading && activeLoanApplications.length === 0 && (
          <div className="card-empty">{t("credit.loadingCurrentLoansEllipsis")}</div>
        )}

        {activeLoanApplications.length > 0 && (
          <div className="approved-offers">
            <div className="approved-offers__header">
              <div>
                <span className="eyebrow">{t("credit.activePendingLoans")}</span>
                <strong>{t("credit.loanRequests", { count: activeLoanApplications.length })}</strong>
              </div>
              <button
                type="button"
                className="button--ghost approved-offers__toggle"
                onClick={() => setAreApprovedOffersExpanded((current) => !current)}
                aria-expanded={areApprovedOffersExpanded}
                aria-controls="approved-offers-list"
              >
                {areApprovedOffersExpanded ? t("credit.retract") : t("credit.showMore")}
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
                      ? t("credit.loanActive")
                      : existingLoan?.status === "PAID" || existingLoan?.status === "CLOSED"
                        ? t("credit.loanClosed")
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
                          <span className="eyebrow">{formatProductType(application.loan_product_type, t)}</span>
                          <h3>{formatMoney(application.offered_amount ?? application.requested_amount, application.currency)}</h3>
                          <p>
                            {isApproved
                              ? t("credit.approvedOn", {
                                  date: application.resolved_at
                                    ? new Date(application.resolved_at).toLocaleDateString()
                                    : t("credit.review"),
                                })
                              : t("credit.submittedOn", { date: new Date(application.created_at).toLocaleDateString() })}
                          </p>
                        </div>
                        <div className="approved-offer-card__actions">
                          <span className={isApproved ? "tag tag--accent" : "tag tag--neutral"}>
                            {isApproved
                              ? t("credit.approved")
                              : needsMoreInfo
                                ? t("credit.moreInfoNeeded")
                                : hasUploadedFollowUpDocuments
                                  ? t("credit.documentsSubmitted")
                                  : t("credit.pendingReview")}
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
                              {activatingApplicationId === application.id ? t("credit.activating") : t("credit.activateLoan")}
                            </button>
                          ) : null}
                        </div>
                      </div>

                      {!isApproved ? (
                        <div className="approved-offer-card__main-payment">
                          <span className="eyebrow">{t("credit.reviewStatus")}</span>
                          <strong>
                            {needsMoreInfo
                              ? t("credit.moreDocumentsNeeded")
                              : hasUploadedFollowUpDocuments
                                ? t("credit.additionalDocsSubmitted")
                                : t("credit.pending")}
                          </strong>
                          <span>
                            {needsMoreInfo
                              ? t("credit.adminNeedsExtraDocs")
                              : hasUploadedFollowUpDocuments
                                ? t("credit.additionalDocsWaiting")
                              : t("credit.adminReviewWillDecide")}
                          </span>
                        </div>
                      ) : breakdown ? (
                        <>
                          <div className="approved-offer-card__main-payment">
                            <span className="eyebrow">{t("credit.monthlyPayment")}</span>
                            <strong>{formatMoney(breakdown.monthly_payment, breakdown.currency)}</strong>
                            <span>
                              {t("credit.aprAndTerm", {
                                rate: application.offered_interest_rate ?? breakdown.annual_interest_rate,
                                months: breakdown.term_months,
                              })}
                            </span>
                            <button
                              type="button"
                              className="button--ghost approved-offer-card__toggle"
                              onClick={() => toggleApprovedOfferDetails(application.id)}
                              aria-expanded={isOfferExpanded}
                              aria-controls={breakdownId}
                            >
                              {isOfferExpanded ? t("credit.retract") : t("credit.showDetails")}
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
                                ? t("credit.loadingPlan")
                                : isPaymentPlanExpanded
                                  ? t("credit.retractPlan")
                                  : t("credit.paymentPlan")}
                            </button>
                          </div>
                          {isOfferExpanded && (
                            <div className="approved-offer-card__details" id={breakdownId}>
                              <div className="approved-offer-card__figures">
                                <div>
                                  <span className="eyebrow">{t("credit.annualRate")}</span>
                                  <strong>{application.offered_interest_rate ?? breakdown.annual_interest_rate}%</strong>
                                </div>
                                <div>
                                  <span className="eyebrow">{t("credit.termEyebrow")}</span>
                                  <strong>{t("credit.monthsSuffix", { count: breakdown.term_months })}</strong>
                                </div>
                                <div>
                                  <span className="eyebrow">{t("credit.totalInterest")}</span>
                                  <strong>{formatMoney(breakdown.total_interest, breakdown.currency)}</strong>
                                </div>
                                <div>
                                  <span className="eyebrow">{t("credit.totalRepayment")}</span>
                                  <strong>{formatMoney(breakdown.total_payment, breakdown.currency)}</strong>
                                </div>
                              </div>
                            </div>
                          )}
                          {isPaymentPlanExpanded && (
                            <div className="loan-payment-plan" id={paymentPlanId}>
                              <div className="loan-payment-plan__header">
                                <div>
                                  <span className="eyebrow">{t("credit.paymentPlan")}</span>
                                  <strong>{t("credit.monthlyPayments", { count: paymentPlanRows.length || breakdown.term_months })}</strong>
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
                                    {t("credit.downloadExcel")}
                                  </button>
                                </div>
                              </div>
                              {paymentPlanError ? (
                                <p className="early-repayment-card__error">{paymentPlanError}</p>
                              ) : paymentPlanRows.length === 0 ? (
                                <p className="approved-offer-card__loading">{t("credit.preparingPaymentPlan")}</p>
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
                                        {t("credit.principalInterest", {
                                          principal: formatMoney(installment.principalAmount, breakdown.currency),
                                          interest: formatMoney(installment.interestAmount, breakdown.currency),
                                        })}
                                      </small>
                                      <small>{t("credit.remaining", { amount: formatMoney(installment.remainingPrincipal, breakdown.currency) })}</small>
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
                                  <span className="eyebrow">{t("credit.earlyRepayment")}</span>
                                  <strong>{t("credit.simulateOrMakePayment")}</strong>
                                </div>
                                <span className="tag tag--neutral">
                                  {t("credit.left", { amount: formatMoney(activeLoan.outstanding_principal, activeLoan.currency) })}
                                </span>
                              </div>
                              {!isAutopayConfigOpen && (
                                <>
                                  <div className="early-repayment-card__form">
                                    <label>
                                      {t("credit.amount")}
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
                                      {t("credit.payFrom")}
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
                                          <option value="">{t("credit.noSourceAvailable")}</option>
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
                                      {simulatingLoanId === activeLoan.id ? t("credit.simulating") : t("credit.simulate")}
                                    </button>
                                <button
                                  type="button"
                                  className="credit-card-payment__submit"
                                      onClick={() => makeEarlyRepayment(activeLoan, repaymentSources)}
                                      disabled={payingLoanId === activeLoan.id || repaymentSources.length === 0}
                                    >
                                      {payingLoanId === activeLoan.id ? t("credit.paying") : t("credit.makePayment")}
                                    </button>
                                  </div>
                                  {selectedRepaymentSource && (
                                    <p className="early-repayment-card__source-balance">
                                      {t("credit.available", {
                                        amount: selectedRepaymentSourceDetails
                                          ? `${formatDecimalAmount(Number(selectedRepaymentSourceDetails.availableBalance))} ${activeLoan.currency}`
                                          : `0.00 ${activeLoan.currency}`,
                                      })}
                                    </p>
                                  )}
                                </>
                              )}
                              <div className="loan-payment-progress">
                                <div className="loan-payment-progress__top">
                                  <span>{t("credit.loanPaid")}</span>
                                  <strong>{loanPaidPercent.toFixed(0)}%</strong>
                                </div>
                                <div className="loan-payment-progress__track" aria-hidden="true">
                                  <span style={{ width: `${loanPaidPercent}%` }} />
                                </div>
                                <div className="loan-payment-progress__figures">
                                  <span>{t("credit.paid", { amount: formatMoney(loanPaidPrincipal.toFixed(2), activeLoan.currency) })}</span>
                                  <span>{t("credit.remainingLabel", { amount: formatMoney(activeLoan.outstanding_principal, activeLoan.currency) })}</span>
                                </div>
                              </div>
                              <div className="early-repayment-card__top">
                                {activeLoan.autopay_enabled && (
                                  <div>
                                    <span className="eyebrow">{t("credit.recurringPayment")}</span>
                                    <strong>
                                      {t("credit.setFor", {
                                        date: new Date(activeLoan.autopay_next_run_on || activeLoan.next_payment_date).toLocaleDateString(),
                                      })}
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
                                        {updatingAutopayLoanId === activeLoan.id ? t("credit.saving") : t("credit.disableRecurring")}
                                      </button>
                                      <button type="button" className="button--ghost" onClick={() => openAutopayConfig(activeLoan)}>
                                        {t("credit.changeSchedule")}
                                      </button>
                                    </>
                                  ) : (
                                    <button type="button" className="button--ghost" onClick={() => openAutopayConfig(activeLoan)}>
                                      {t("credit.setUpRecurring")}
                                    </button>
                                  )}
                                </div>
                              </div>
                              {isAutopayConfigOpen && (
                                <div className="early-repayment-card__form">
                                  <label>
                                    {t("credit.payFrom")}
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
                                        <option value="">{t("credit.noAccountOrCard")}</option>
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
                                    {t("credit.amount")}
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
                                    {t("credit.paymentDate")}
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
                                      ? t("credit.saving")
                                      : activeLoan.autopay_enabled
                                        ? t("credit.updateRecurring")
                                        : t("credit.enableRecurring")}
                                  </button>
                                  <button type="button" className="button--ghost early-repayment-card__simulate" onClick={() => closeAutopayConfig(activeLoan.id)}>
                                    {t("credit.cancel")}
                                  </button>
                                </div>
                              )}
                              {earlyRepaymentError && <p className="early-repayment-card__error">{earlyRepaymentError}</p>}
                              {earlyRepaymentMessage && <p className="early-repayment-card__message">{earlyRepaymentMessage}</p>}
                              {earlyRepaymentResult && (
                                <div className="early-repayment-card__result">
                                  <div>
                                    <span>{t("credit.interestSaved")}</span>
                                    <strong>
                                      {formatMoney(earlyRepaymentResult.total_interest_saved, earlyRepaymentResult.currency)}
                                    </strong>
                                  </div>
                                  <div>
                                    <span>{t("credit.shorterBy")}</span>
                                    <strong>{t("credit.monthsSuffix", { count: earlyRepaymentResult.term_months_reduced })}</strong>
                                  </div>
                                  <div>
                                    <span>{t("credit.newBalance")}</span>
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
                          {t("credit.preparingBreakdown")}
                        </div>
                      )}
                      {needsMoreInfo && (
                        <div className="loan-more-info-upload">
                          <div className="loan-more-info-upload__copy">
                            <span className="eyebrow">{t("credit.requestedDocuments")}</span>
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
                              {t("credit.uploadFiles")}
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
                              {uploadingMoreInfoApplicationId === application.id ? t("credit.uploading") : t("credit.sendDocuments")}
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
                <span className="eyebrow">{t("credit.pastLoans")}</span>
                <strong>{t("credit.closedLoans", { count: closedLoanApplications.length })}</strong>
              </div>
              <button
                type="button"
                className="button--ghost approved-offers__toggle"
                onClick={() => setArePastLoansExpanded((current) => !current)}
                aria-expanded={arePastLoansExpanded}
                aria-controls="past-loans-list"
              >
                {arePastLoansExpanded ? t("credit.retract") : t("credit.showMore")}
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
                          <span className="eyebrow">{formatProductType(application.loan_product_type, t)}</span>
                          <h3>{formatMoney(application.offered_amount ?? application.requested_amount, application.currency)}</h3>
                          <p>
                            {t("credit.closedOn", {
                              date: closedLoan?.closed_at
                                ? new Date(closedLoan.closed_at).toLocaleDateString()
                                : t("credit.afterRepayment"),
                            })}
                          </p>
                        </div>
                        <div className="approved-offer-card__actions">
                          <span className="tag tag--neutral">{t("credit.loanClosed")}</span>
                        </div>
                      </div>
                      <div className="approved-offer-card__details">
                        <div className="approved-offer-card__figures">
                          <div>
                            <span className="eyebrow">{t("credit.originalPrincipal")}</span>
                            <strong>{formatMoney(closedLoan?.principal_amount ?? application.offered_amount ?? application.requested_amount, application.currency)}</strong>
                          </div>
                          <div>
                            <span className="eyebrow">{t("credit.outstanding")}</span>
                            <strong>{formatMoney(closedLoan?.outstanding_principal ?? "0.00", closedLoan?.currency ?? application.currency)}</strong>
                          </div>
                          <div>
                            <span className="eyebrow">{t("credit.monthlyPayment")}</span>
                            <strong>
                              {closedLoan
                                ? formatMoney(closedLoan.monthly_payment, closedLoan.currency)
                                : breakdown
                                  ? formatMoney(breakdown.monthly_payment, breakdown.currency)
                                  : t("credit.closed")}
                            </strong>
                          </div>
                          <div>
                            <span className="eyebrow">{t("credit.termEyebrow")}</span>
                            <strong>{t("credit.monthsSuffix", { count: closedLoan?.term_months ?? breakdown?.term_months ?? application.requested_term_months ?? 0 })}</strong>
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

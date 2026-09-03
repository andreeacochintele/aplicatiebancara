import { Download } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { ApiError, apiRequest } from "../api/apiClient";
import { QrCode } from "../components/QrCode";
import { BILL_SPLIT_CHANGED_EVENT } from "../events";
import { downloadQrPng } from "../features/payments/qrImage";
import { useAuth } from "../hooks/useAuth";
import type {
  Beneficiary,
  BillSplit,
  FXQuote,
  PaymentRequest,
  ScheduledPayment,
  ScheduledPaymentFrequency,
  ScheduledPaymentStatus,
  Transaction,
  TransactionFolder,
  Wallet,
} from "../types";
import { formatIban } from "../utils";

type PaymentTab = "transfer" | "phone" | "qr" | "scheduled" | "folders";

interface TransferFormState {
  beneficiary: string;
  iban: string;
  source_wallet_id: string;
  amount: string;
  currency: string;
  description: string;
  save_beneficiary: boolean;
  is_favorite: boolean;
}

interface PhoneFormState {
  phone: string;
  source_wallet_id: string;
  amount: string;
  description: string;
}

interface PhoneRecipientPreview {
  user_id: string;
  first_name: string;
  last_name: string;
  phone: string;
  destination_wallet_id: string;
  destination_wallet_currency: string;
}

interface QrRequestFormState {
  destination_wallet_id: string;
  amount: string;
  expires_in_minutes: string;
  reference: string;
  note: string;
}

interface QrPayFormState {
  request_id: string;
  source_wallet_id: string;
  amount: string;
}

interface ScheduledFormState {
  beneficiary_name: string;
  iban: string;
  source_wallet_id: string;
  amount: string;
  currency: string;
  frequency: ScheduledPaymentFrequency;
  next_run_on: string;
  notify_days_before: string;
  description: string;
}

interface FolderSplitParticipantDraft {
  key: string;
  name: string;
  phone: string;
  percent: string;
}

function dateInputValue(offsetDays: number): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

const EMPTY_TRANSFER_FORM: TransferFormState = {
  beneficiary: "",
  iban: "",
  source_wallet_id: "",
  amount: "",
  currency: "RON",
  description: "",
  save_beneficiary: false,
  is_favorite: false,
};

const EMPTY_PHONE_FORM: PhoneFormState = {
  phone: "",
  source_wallet_id: "",
  amount: "",
  description: "",
};

const EMPTY_QR_FORM: QrRequestFormState = {
  destination_wallet_id: "",
  amount: "",
  expires_in_minutes: "15",
  reference: "",
  note: "",
};

const EMPTY_QR_PAY_FORM: QrPayFormState = {
  request_id: "",
  source_wallet_id: "",
  amount: "",
};

const EMPTY_SCHEDULED_FORM: ScheduledFormState = {
  beneficiary_name: "",
  iban: "",
  source_wallet_id: "",
  amount: "",
  currency: "RON",
  frequency: "MONTHLY",
  next_run_on: dateInputValue(1),
  notify_days_before: "3",
  description: "",
};

const TABS: Array<{ id: PaymentTab; labelKey: string }> = [
  { id: "transfer", labelKey: "payments.transfer" },
  { id: "phone", labelKey: "payments.byPhone" },
  { id: "qr", labelKey: "payments.qrRequest" },
  { id: "scheduled", labelKey: "payments.scheduled" },
  { id: "folders", labelKey: "payments.folders" },
];

const SCHEDULED_FREQUENCIES: ScheduledPaymentFrequency[] = ["ONCE", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"];

function compact(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function beneficiarySubtitle(beneficiary: Beneficiary, t: (key: string) => string): string {
  const details = [beneficiary.iban ? formatIban(beneficiary.iban) : null, beneficiary.phone].filter(Boolean);
  return details.length > 0 ? details.join(" - ") : t("payments.internalBeneficiary");
}

function walletLabel(wallet: Wallet): string {
  const base = wallet.nickname ? `${wallet.currency} — ${wallet.nickname}` : wallet.currency;
  return `${base} - ${wallet.available_balance}`;
}

function walletCurrency(wallets: Wallet[], walletId: string): string {
  return wallets.find((wallet) => wallet.id === walletId)?.currency ?? "RON";
}

function normalizePhone(value: string): string {
  return value.replace(/\s/g, "");
}

function folderSplitMarker(folderId: string): string {
  return `[folder:${folderId}]`;
}

// Money coming in only (not a self-transfer between the user's own wallets).
// Mirrors TransactionsPage's isIncomingOnly.
function isIncomingOnly(transaction: Transaction, userWalletIds: Set<string>): boolean {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  return isIncoming && !isOutgoing;
}

function sortBeneficiaries(list: Beneficiary[]): Beneficiary[] {
  return [...list].sort((left, right) => {
    if (left.is_favorite !== right.is_favorite) {
      return left.is_favorite ? -1 : 1;
    }
    return left.name.localeCompare(right.name);
  });
}

export function PaymentsPage() {
  const { t } = useTranslation();
  const { accessToken, user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const highlightedFolderId = searchParams.get("folder") ?? "";
  const [activeTab, setActiveTab] = useState<PaymentTab>("transfer");
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [form, setForm] = useState<TransferFormState>(EMPTY_TRANSFER_FORM);
  const [phoneForm, setPhoneForm] = useState<PhoneFormState>(EMPTY_PHONE_FORM);
  const [phonePreview, setPhonePreview] = useState<PhoneRecipientPreview | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [phoneNotice, setPhoneNotice] = useState<string | null>(null);
  const [qrForm, setQrForm] = useState<QrRequestFormState>(EMPTY_QR_FORM);
  const [qrPayForm, setQrPayForm] = useState<QrPayFormState>(EMPTY_QR_PAY_FORM);
  const [scheduledForm, setScheduledForm] = useState<ScheduledFormState>(EMPTY_SCHEDULED_FORM);
  const [qrRequest, setQrRequest] = useState<PaymentRequest | null>(null);
  const [qrLookup, setQrLookup] = useState<PaymentRequest | null>(null);
  const [scheduledPayments, setScheduledPayments] = useState<ScheduledPayment[]>([]);
  const [billSplits, setBillSplits] = useState<BillSplit[]>([]);
  const [transactionFolders, setTransactionFolders] = useState<TransactionFolder[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [transferQuote, setTransferQuote] = useState<FXQuote | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);
  const [qrNotice, setQrNotice] = useState<string | null>(null);
  const [scheduledError, setScheduledError] = useState<string | null>(null);
  const [scheduledNotice, setScheduledNotice] = useState<string | null>(null);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [walletsLoading, setWalletsLoading] = useState(false);
  const [phoneLookingUp, setPhoneLookingUp] = useState(false);
  const [phoneSending, setPhoneSending] = useState(false);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [scheduledLoading, setScheduledLoading] = useState(false);
  const [scheduledSubmitting, setScheduledSubmitting] = useState(false);
  const [folderLoading, setFolderLoading] = useState(false);
  const [qrCreating, setQrCreating] = useState(false);
  const [qrLookingUp, setQrLookingUp] = useState(false);
  const [qrPaying, setQrPaying] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [scheduledActionId, setScheduledActionId] = useState<string | null>(null);
  const [splitActionId, setSplitActionId] = useState<string | null>(null);
  const [folderActionId, setFolderActionId] = useState<string | null>(null);
  const [folderSplitTarget, setFolderSplitTarget] = useState<TransactionFolder | null>(null);
  const [folderSplitParticipants, setFolderSplitParticipants] = useState<FolderSplitParticipantDraft[]>([]);
  // Guards createFolderBillSplit against a double submit -- a ref updates
  // synchronously, unlike folderActionId state, which can lag a render
  // behind a fast double-click/double-Enter and let two requests through.
  const folderSplitSubmittingRef = useRef(false);

  async function loadBeneficiaries() {
    if (!accessToken) return;
    setLoading(true);
    try {
      const list = await apiRequest<Beneficiary[]>("/payments/beneficiaries", { token: accessToken });
      setBeneficiaries(sortBeneficiaries(list));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("payments.couldNotLoadBeneficiaries"));
    } finally {
      setLoading(false);
    }
  }

  async function loadWallets() {
    if (!accessToken) return;
    setWalletsLoading(true);
    try {
      const list = await apiRequest<Wallet[]>("/wallets", { token: accessToken });
      setWallets(list);
      const defaultWallet = list.find((wallet) => wallet.is_main) ?? list[0];
      if (defaultWallet) {
        setForm((current) =>
          current.source_wallet_id
            ? current
            : { ...current, source_wallet_id: defaultWallet.id, currency: defaultWallet.currency },
        );
        setPhoneForm((current) =>
          current.source_wallet_id ? current : { ...current, source_wallet_id: defaultWallet.id },
        );
        setQrForm((current) =>
          current.destination_wallet_id ? current : { ...current, destination_wallet_id: defaultWallet.id },
        );
        setQrPayForm((current) =>
          current.source_wallet_id ? current : { ...current, source_wallet_id: defaultWallet.id },
        );
        setScheduledForm((current) =>
          current.source_wallet_id
            ? current
            : { ...current, source_wallet_id: defaultWallet.id, currency: defaultWallet.currency },
        );
      }
    } catch (err) {
      setPhoneError(err instanceof ApiError ? err.message : t("payments.couldNotLoadWallets"));
    } finally {
      setWalletsLoading(false);
    }
  }

  useEffect(() => {
    void loadBeneficiaries();
    void loadWallets();
    void loadScheduledPayments();
    void loadBillSplits();
    void loadTransactionFolders();
    void loadTransactions();
  }, [accessToken]);

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && TABS.some((item) => item.id === tab)) {
      setActiveTab(tab as PaymentTab);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!accessToken) return;
    function handleBillSplitChanged() {
      void loadBillSplits();
      void loadTransactionFolders();
    }
    window.addEventListener(BILL_SPLIT_CHANGED_EVENT, handleBillSplitChanged);
    return () => window.removeEventListener(BILL_SPLIT_CHANGED_EVENT, handleBillSplitChanged);
  }, [accessToken]);

  async function loadScheduledPayments() {
    if (!accessToken) return;
    setScheduledLoading(true);
    try {
      const list = await apiRequest<ScheduledPayment[]>("/payments/scheduled-payments", { token: accessToken });
      setScheduledPayments(list);
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : t("payments.couldNotLoadScheduled"));
    } finally {
      setScheduledLoading(false);
    }
  }

  async function loadBillSplits() {
    if (!accessToken) return;
    try {
      const list = await apiRequest<BillSplit[]>("/payments/bill-splits", { token: accessToken });
      setBillSplits(list);
    } catch {
      // Background refresh (folder split status, cancel) -- no dedicated
      // display for this; the caller's own error state covers user actions.
    }
  }

  async function loadTransactionFolders() {
    if (!accessToken) return;
    setFolderLoading(true);
    setFolderError(null);
    try {
      const list = await apiRequest<TransactionFolder[]>("/payments/transaction-folders", { token: accessToken });
      setTransactionFolders(list);
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : t("payments.couldNotLoadFolders"));
    } finally {
      setFolderLoading(false);
    }
  }

  async function loadTransactions() {
    if (!accessToken) return;
    try {
      const list = await apiRequest<Transaction[]>("/transactions", { token: accessToken });
      setTransactions(list);
    } catch {
      setTransactions([]);
    }
  }

  function resetForm() {
    setForm((current) => ({
      ...EMPTY_TRANSFER_FORM,
      source_wallet_id: current.source_wallet_id,
      currency: current.currency,
    }));
    setTransferQuote(null);
  }

  function clearTransferQuote() {
    setTransferQuote(null);
    setNotice(null);
  }

  async function handleGetFxQuote() {
    if (!accessToken) return;
    setQuoteLoading(true);
    setError(null);
    setNotice(null);
    setTransferQuote(null);
    try {
      const quote = await apiRequest<FXQuote>("/payments/transfers/iban/fx-quote", {
        method: "POST",
        token: accessToken,
        body: {
          source_wallet_id: form.source_wallet_id,
          amount: form.amount,
          currency: form.currency,
        },
      });
      setTransferQuote(quote);
      setNotice(t("payments.fxQuoteReady"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("payments.couldNotCreateFxQuote"));
    } finally {
      setQuoteLoading(false);
    }
  }

  async function handleIbanTransfer(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;

    const sourceWallet = wallets.find((wallet) => wallet.id === form.source_wallet_id);
    const needsFxQuote = Boolean(sourceWallet && sourceWallet.currency !== form.currency);
    if (needsFxQuote && !transferQuote) {
      await handleGetFxQuote();
      return;
    }

    setSubmitting(true);
    setError(null);
    setNotice(null);

    const payload = {
      beneficiary_name: form.beneficiary.trim(),
      iban: form.iban.trim(),
      source_wallet_id: form.source_wallet_id,
      amount: needsFxQuote && transferQuote ? transferQuote.target_amount : form.amount,
      currency: form.currency,
      description: compact(form.description),
      save_beneficiary: form.save_beneficiary,
      is_favorite: form.is_favorite,
      fx_quote_id: needsFxQuote ? transferQuote?.id : null,
    };

    try {
      const transaction = await apiRequest<Transaction>("/payments/transfers/iban", {
        method: "POST",
        token: accessToken,
        body: payload,
      });
      setNotice(t("payments.transferCompleted", { amount: transaction.amount, currency: transaction.currency }));
      resetForm();
      await loadWallets();
      await loadBeneficiaries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("payments.couldNotCompleteTransfer"));
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleFavorite(beneficiary: Beneficiary) {
    if (!accessToken) return;
    setError(null);
    setNotice(null);
    setActionId(beneficiary.id);
    try {
      const updated = await apiRequest<Beneficiary>(`/payments/beneficiaries/${beneficiary.id}`, {
        method: "PATCH",
        token: accessToken,
        body: { is_favorite: !beneficiary.is_favorite },
      });
      setBeneficiaries((current) => sortBeneficiaries(current.map((item) => (item.id === updated.id ? updated : item))));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("payments.couldNotUpdateFavorite"));
    } finally {
      setActionId(null);
    }
  }

  async function deleteBeneficiary(beneficiary: Beneficiary) {
    if (!accessToken) return;
    setError(null);
    setNotice(null);
    setActionId(beneficiary.id);
    try {
      await apiRequest<void>(`/payments/beneficiaries/${beneficiary.id}`, {
        method: "DELETE",
        token: accessToken,
      });
      setNotice(t("payments.beneficiaryDeleted"));
      await loadBeneficiaries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("payments.couldNotDeleteBeneficiary"));
    } finally {
      setActionId(null);
    }
  }

  async function handlePhoneLookup() {
    if (!accessToken || !phoneForm.phone.trim()) return;
    setPhoneLookingUp(true);
    setPhoneError(null);
    setPhoneNotice(null);
    setPhonePreview(null);
    const phone = normalizePhone(phoneForm.phone);
    try {
      const preview = await apiRequest<PhoneRecipientPreview>("/payments/phone/lookup", {
        method: "POST",
        token: accessToken,
        body: { phone },
      });
      setPhonePreview(preview);
    } catch (err) {
      const saved = beneficiaries.find((beneficiary) => beneficiary.phone && normalizePhone(beneficiary.phone) === phone);
      if (saved) {
        setPhoneError(t("payments.savedNotLinked", { name: saved.name }));
      } else {
        setPhoneError(err instanceof ApiError ? err.message : t("payments.couldNotFindPhone"));
      }
    } finally {
      setPhoneLookingUp(false);
    }
  }

  async function handlePhoneTransfer(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || !phonePreview) return;
    setPhoneSending(true);
    setPhoneError(null);
    setPhoneNotice(null);
    try {
      const transaction = await apiRequest<Transaction>("/payments/phone/transfer", {
        method: "POST",
        token: accessToken,
        body: {
          phone: normalizePhone(phoneForm.phone),
          source_wallet_id: phoneForm.source_wallet_id,
          amount: phoneForm.amount,
          description: compact(phoneForm.description),
        },
      });
      setPhoneNotice(t("payments.transferCompleted", { amount: transaction.amount, currency: transaction.currency }));
      setPhoneForm((current) => ({ ...current, amount: "", description: "" }));
      await loadWallets();
    } catch (err) {
      setPhoneError(err instanceof ApiError ? err.message : t("payments.couldNotCompleteTransfer"));
    } finally {
      setPhoneSending(false);
    }
  }

  async function handleQrCreate(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setQrCreating(true);
    setQrError(null);
    setQrNotice(null);
    try {
      const paymentRequest = await apiRequest<PaymentRequest>("/payments/payment-requests", {
        method: "POST",
        token: accessToken,
        body: {
          destination_wallet_id: qrForm.destination_wallet_id,
          amount: compact(qrForm.amount),
          currency: walletCurrency(wallets, qrForm.destination_wallet_id),
          expires_in_minutes: Number(qrForm.expires_in_minutes),
          reference: qrForm.reference.trim() || null,
          note: qrForm.note.trim() || null,
        },
      });
      setQrRequest(paymentRequest);
      setQrPayForm((current) => ({ ...current, request_id: paymentRequest.id }));
      setQrNotice(t("payments.paymentRequestCreated"));
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : t("payments.couldNotCreatePaymentRequest"));
    } finally {
      setQrCreating(false);
    }
  }

  async function handleQrLookup() {
    if (!accessToken || !qrPayForm.request_id.trim()) return;
    setQrLookingUp(true);
    setQrError(null);
    setQrNotice(null);
    setQrLookup(null);
    try {
      const paymentRequest = await apiRequest<PaymentRequest>(
        `/payments/payment-requests/${qrPayForm.request_id.trim()}`,
        { token: accessToken },
      );
      setQrLookup(paymentRequest);
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : t("payments.couldNotLoadPaymentRequest"));
    } finally {
      setQrLookingUp(false);
    }
  }

  async function handleQrPay(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setQrPaying(true);
    setQrError(null);
    setQrNotice(null);
    try {
      const transaction = await apiRequest<Transaction>(`/payments/payment-requests/${qrPayForm.request_id.trim()}/pay`, {
        method: "POST",
        token: accessToken,
        body: {
          source_wallet_id: qrPayForm.source_wallet_id,
          amount: compact(qrPayForm.amount),
          description: t("payments.qrPaymentDescription"),
        },
      });
      setQrNotice(t("payments.qrPaymentCompleted", { amount: transaction.amount, currency: transaction.currency }));
      setQrLookup(null);
      setQrPayForm((current) => ({ ...current, amount: "" }));
      await loadWallets();
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : t("payments.couldNotPayRequest"));
    } finally {
      setQrPaying(false);
    }
  }

  function resetScheduledForm() {
    setScheduledForm((current) => ({
      ...EMPTY_SCHEDULED_FORM,
      source_wallet_id: current.source_wallet_id,
      currency: current.currency,
    }));
  }

  async function handleScheduledSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setScheduledSubmitting(true);
    setScheduledError(null);
    setScheduledNotice(null);
    try {
      await apiRequest<ScheduledPayment>("/payments/scheduled-payments", {
        method: "POST",
        token: accessToken,
        body: {
          beneficiary_name: scheduledForm.beneficiary_name.trim(),
          iban: scheduledForm.iban.trim(),
          source_wallet_id: scheduledForm.source_wallet_id,
          amount: scheduledForm.amount,
          currency: scheduledForm.currency,
          frequency: scheduledForm.frequency,
          next_run_on: scheduledForm.next_run_on,
          notify_days_before: Number(scheduledForm.notify_days_before),
          description: compact(scheduledForm.description),
        },
      });
      setScheduledNotice(t("payments.scheduledPaymentCreated"));
      resetScheduledForm();
      await loadScheduledPayments();
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : t("payments.couldNotCreateScheduled"));
    } finally {
      setScheduledSubmitting(false);
    }
  }

  async function updateScheduledStatus(payment: ScheduledPayment, status: ScheduledPaymentStatus) {
    if (!accessToken) return;
    setScheduledActionId(payment.id);
    setScheduledError(null);
    setScheduledNotice(null);
    try {
      await apiRequest<ScheduledPayment>(`/payments/scheduled-payments/${payment.id}`, {
        method: "PATCH",
        token: accessToken,
        body: { status },
      });
      setScheduledNotice(t("payments.scheduledPaymentStatus", { status: t(`payments.scheduledStatus.${status.toLowerCase()}`, { defaultValue: status.toLowerCase() }) }));
      await loadScheduledPayments();
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : t("payments.couldNotUpdateScheduled"));
    } finally {
      setScheduledActionId(null);
    }
  }

  async function deleteScheduledPayment(payment: ScheduledPayment) {
    if (!accessToken) return;
    setScheduledActionId(payment.id);
    setScheduledError(null);
    setScheduledNotice(null);
    try {
      await apiRequest<void>(`/payments/scheduled-payments/${payment.id}`, {
        method: "DELETE",
        token: accessToken,
      });
      setScheduledNotice(t("payments.scheduledPaymentDeleted"));
      await loadScheduledPayments();
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : t("payments.couldNotDeleteScheduled"));
    } finally {
      setScheduledActionId(null);
    }
  }

  async function cancelBillSplit(split: BillSplit) {
    if (!accessToken) return;
    setSplitActionId(split.id);
    setFolderError(null);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/cancel`, {
        method: "PATCH",
        token: accessToken,
      });
      await loadBillSplits();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : t("payments.couldNotCancelSplit"));
    } finally {
      setSplitActionId(null);
    }
  }

  const userWalletIds = new Set(wallets.map((wallet) => wallet.id));

  function folderTransactions(folder: TransactionFolder): Transaction[] {
    const ids = new Set(folder.items.map((item) => item.transaction_id));
    return transactions.filter((transaction) => ids.has(transaction.id));
  }

  function folderSplitData(folder: TransactionFolder) {
    const relatedTransactions = folderTransactions(folder);
    const currencies = Array.from(new Set(relatedTransactions.map((transaction) => transaction.currency)));
    const currency = currencies.length === 1 ? currencies[0] : "";
    // Money received (cashback, refunds, etc.) reduces what's actually owed,
    // rather than adding to the bill.
    const total = relatedTransactions.reduce((sum, transaction) => {
      const amount = Number(transaction.amount);
      return isIncomingOnly(transaction, userWalletIds) ? sum - amount : sum + amount;
    }, 0);
    const folderSplits = billSplits.filter(
      (candidate) => candidate.owner_user_id === user?.id && candidate.description?.includes(folderSplitMarker(folder.id)),
    );
    const settledSplit = folderSplits.find((candidate) => candidate.status === "SETTLED");
    const waitingSplit = folderSplits.find(
      (candidate) =>
        candidate.status === "OPEN" &&
        candidate.participants.every((participant) => participant.status !== "DECLINED"),
    );
    const refusedSplit = folderSplits.find(
      (candidate) =>
        candidate.status === "OPEN" &&
        candidate.participants.some((participant) => participant.status === "DECLINED"),
    );
    const split = settledSplit ?? waitingSplit ?? refusedSplit ?? folderSplits[0];
    return {
      currency,
      hasDeclinedSplit: Boolean(refusedSplit),
      hasMixedCurrencies: currencies.length > 1,
      split,
      total: total.toFixed(2),
      transactions: relatedTransactions,
    };
  }

  function openFolderSplit(folder: TransactionFolder) {
    setFolderError(null);
    setFolderSplitTarget(folder);
    setFolderSplitParticipants([]);
  }

  function addFolderSplitParticipant() {
    setFolderError(null);
    setFolderSplitParticipants((current) => [
      ...current,
      { key: crypto.randomUUID(), name: "", phone: "", percent: "" },
    ]);
  }

  function updateFolderSplitParticipant(key: string, changes: Partial<FolderSplitParticipantDraft>) {
    setFolderError(null);
    setFolderSplitParticipants((current) =>
      current.map((participant) => (participant.key === key ? { ...participant, ...changes } : participant)),
    );
  }

  function removeFolderSplitParticipant(key: string) {
    setFolderError(null);
    setFolderSplitParticipants((current) => current.filter((participant) => participant.key !== key));
  }

  function splitFolderEqually() {
    setFolderSplitParticipants((current) => {
      if (current.length === 0) return current;
      const percent = (100 / (current.length + 1)).toFixed(2);
      return current.map((participant) => ({ ...participant, percent }));
    });
  }

  async function createFolderBillSplit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || !folderSplitTarget) return;
    if (folderSplitSubmittingRef.current) return;
    const data = folderSplitData(folderSplitTarget);
    const participants = folderSplitParticipants
      .map((participant) => ({
        name: participant.name.trim(),
        phone: normalizePhone(participant.phone),
        percent: Number(participant.percent),
      }))
      .filter((participant) => participant.name.length > 0 && participant.phone.length > 0);
    const percentTotal = folderSplitParticipants.reduce((sum, participant) => {
      const value = Number(participant.percent);
      return Number.isFinite(value) ? sum + value : sum;
    }, 0);
    if (data.transactions.length === 0) {
      setFolderError(t("payments.folderNoTransactions"));
      return;
    }
    if (data.hasMixedCurrencies || !data.currency) {
      setFolderError(t("payments.folderMixedCurrencies"));
      return;
    }
    if (participants.length === 0) {
      setFolderError(t("payments.addAtLeastOneRecipient"));
      return;
    }
    if (percentTotal > 100) {
      setFolderError(t("payments.splitExceeds100"));
      return;
    }
    if (Number(data.total) <= 0) {
      setFolderError(t("payments.netTotalNotPositive"));
      return;
    }

    folderSplitSubmittingRef.current = true;
    setFolderActionId(folderSplitTarget.id);
    setFolderError(null);
    try {
      await apiRequest<BillSplit>("/payments/bill-splits", {
        method: "POST",
        token: accessToken,
        body: {
          title: t("payments.folderSplitTitle", { name: folderSplitTarget.name }),
          total_amount: data.total,
          currency: data.currency,
          description: t("payments.folderSplitDescription", { marker: folderSplitMarker(folderSplitTarget.id), name: folderSplitTarget.name }),
          participants: participants.map(({ name, phone, percent }) => ({
            name,
            phone,
            percent: percent.toFixed(2),
          })),
        },
      });
      setFolderSplitTarget(null);
      setFolderSplitParticipants([]);
      await loadBillSplits();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : t("payments.couldNotSplitFolder"));
    } finally {
      setFolderActionId(null);
      folderSplitSubmittingRef.current = false;
    }
  }

  async function deleteTransactionFolder(folder: TransactionFolder) {
    if (!accessToken) return;
    setFolderActionId(folder.id);
    setFolderError(null);
    try {
      await apiRequest<void>(`/payments/transaction-folders/${folder.id}`, {
        method: "DELETE",
        token: accessToken,
      });
      if (highlightedFolderId === folder.id) {
        setSearchParams({ tab: "folders" });
      }
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : t("payments.couldNotDeleteFolder"));
    } finally {
      setFolderActionId(null);
    }
  }

  async function removeTransactionFromFolder(folder: TransactionFolder, transactionId: string) {
    if (!accessToken) return;
    setFolderActionId(transactionId);
    setFolderError(null);
    try {
      await apiRequest<void>(`/payments/transaction-folders/${folder.id}/transactions/${transactionId}`, {
        method: "DELETE",
        token: accessToken,
      });
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : t("payments.couldNotRemoveFromFolder"));
    } finally {
      setFolderActionId(null);
    }
  }

  const transferWallet = wallets.find((wallet) => wallet.id === form.source_wallet_id);
  const transferCurrencies = Array.from(new Set(wallets.map((wallet) => wallet.currency)));
  const hasTransferCurrencyMismatch = Boolean(transferWallet && transferWallet.currency !== form.currency);
  const scheduledWallet = wallets.find((wallet) => wallet.id === scheduledForm.source_wallet_id);
  const hasScheduledCurrencyMismatch = Boolean(scheduledWallet && scheduledWallet.currency !== scheduledForm.currency);
  const folderSplitPercentTotal = folderSplitParticipants.reduce((sum, participant) => {
    const value = Number(participant.percent);
    return Number.isFinite(value) ? sum + value : sum;
  }, 0);
  const folderSplitExceedsTotal = folderSplitPercentTotal > 100;

  return (
    <section className="payments-page">
      <div className="payment-tabs" role="tablist" aria-label={t("payments.paymentFlows")}>
        {TABS.map((tab) => (
          <button
            className={activeTab === tab.id ? "payment-tabs__button active" : "payment-tabs__button"}
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id);
              setSearchParams(tab.id === "transfer" ? {} : { tab: tab.id });
            }}
            type="button"
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {activeTab === "transfer" ? (
        <div className="payments-grid">
          <form className="tile transfer-form-card" onSubmit={handleIbanTransfer}>
            <div>
              <span className="eyebrow">{t("payments.details")}</span>
              <h2>{t("payments.newTransfer")}</h2>
            </div>

            <label>
              {t("payments.beneficiary")}
              <input
                onChange={(event) => {
                  setForm((current) => ({ ...current, beneficiary: event.target.value }));
                  clearTransferQuote();
                }}
                required
                value={form.beneficiary}
              />
            </label>

            <label>
              {t("payments.iban")}
              <input
                onChange={(event) => {
                  setForm((current) => ({ ...current, iban: event.target.value }));
                  clearTransferQuote();
                }}
                placeholder="RO49 AAAA 1B31 0075 9384 0000"
                value={form.iban}
              />
            </label>

            <div className="amount-row">
              <label>
                {t("payments.amount")}
                <input
                  min="0.01"
                  onChange={(event) => {
                    setForm((current) => ({ ...current, amount: event.target.value }));
                    clearTransferQuote();
                  }}
                  required
                  step="0.01"
                  type="number"
                  value={form.amount}
                />
              </label>

              <label>
                {t("payments.currency")}
                <select
                  onChange={(event) => {
                    setForm((current) => ({ ...current, currency: event.target.value }));
                    clearTransferQuote();
                  }}
                  required
                  value={form.currency}
                >
                  {(transferCurrencies.length > 0 ? transferCurrencies : ["RON"]).map((currency) => (
                    <option key={currency} value={currency}>
                      {currency}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label>
              {t("payments.payFrom")}
              <select
                disabled={walletsLoading}
                onChange={(event) => {
                  setForm((current) => ({
                    ...current,
                    source_wallet_id: event.target.value,
                  }));
                  clearTransferQuote();
                }}
                required
                value={form.source_wallet_id}
              >
                {wallets.map((wallet) => (
                  <option key={wallet.id} value={wallet.id}>
                    {walletLabel(wallet)}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t("payments.description")}
              <input
                onChange={(event) => {
                  setForm((current) => ({ ...current, description: event.target.value }));
                  clearTransferQuote();
                }}
                placeholder={t("payments.descriptionPlaceholderRent")}
                value={form.description}
              />
            </label>

            <label className="checkbox-row">
              <input
                checked={form.save_beneficiary}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    save_beneficiary: event.target.checked,
                    is_favorite: event.target.checked ? current.is_favorite : false,
                  }))
                }
                type="checkbox"
              />
              {t("payments.saveBeneficiary")}
            </label>

            {form.save_beneficiary && (
              <label className="checkbox-row">
                <input
                  checked={form.is_favorite}
                  onChange={(event) => setForm((current) => ({ ...current, is_favorite: event.target.checked }))}
                  type="checkbox"
                />
                {t("payments.favorite")}
              </label>
            )}

            {hasTransferCurrencyMismatch && transferWallet && !transferQuote && (
              <p className="status-line">
                {t("payments.fxQuoteRequired", { currency: transferWallet.currency })}
              </p>
            )}

            {transferQuote && (
              <div className="fx-quote-card">
                <span className="eyebrow">{t("payments.fxQuote")}</span>
                <div className="quote-row">
                  <span>{t("payments.debit")}</span>
                  <strong>
                    {transferQuote.source_amount} {transferQuote.source_currency}
                  </strong>
                </div>
                <div className="quote-row">
                  <span>{t("payments.recipientReceives")}</span>
                  <strong>
                    {transferQuote.target_amount} {transferQuote.target_currency}
                  </strong>
                </div>
                <div className="quote-row">
                  <span>{t("payments.rate")}</span>
                  <strong>{transferQuote.exchange_rate}</strong>
                </div>
                <div className="quote-row">
                  <span>{t("payments.fee")}</span>
                  <strong>
                    {transferQuote.fee} {transferQuote.source_currency}
                  </strong>
                </div>
                <span className="quote-expiry">{t("payments.expires", { time: new Date(transferQuote.expires_at).toLocaleTimeString() })}</span>
              </div>
            )}
            {error && <p className="status-line status-line--error">{error}</p>}
            {notice && <p className="status-line">{notice}</p>}

            <div className="form-actions">
              <button
                disabled={
                  submitting ||
                  quoteLoading ||
                  !form.beneficiary.trim() ||
                  !form.iban.trim() ||
                  !form.source_wallet_id ||
                  !form.amount
                }
                type="submit"
              >
                {submitting
                  ? t("payments.sending")
                  : quoteLoading
                    ? t("payments.gettingQuote")
                    : hasTransferCurrencyMismatch && !transferQuote
                      ? t("payments.getFxQuote")
                      : hasTransferCurrencyMismatch
                        ? t("payments.acceptQuoteAndSend")
                        : form.save_beneficiary
                          ? t("payments.sendAndSave")
                          : t("payments.sendTransfer")}
              </button>
              <button className="button--ghost" onClick={resetForm} type="button">
                {t("payments.clear")}
              </button>
            </div>
          </form>

          <div className="payments-side">
            <section className="tile saved-beneficiaries">
              <div className="tile__header">
                <span className="eyebrow">{t("payments.savedBeneficiaries")}</span>
                {loading && <span className="tag tag--neutral">{t("payments.loading")}</span>}
              </div>

              <div className="beneficiary-list">
                {beneficiaries.map((beneficiary) => (
                  <div
                    className={beneficiary.is_favorite ? "beneficiary-row beneficiary-row--favorite" : "beneficiary-row"}
                    key={beneficiary.id}
                  >
                    <span className="beneficiary-avatar">{initials(beneficiary.name)}</span>
                    <div className="beneficiary-meta">
                      <div className="beneficiary-title">
                        <strong>{beneficiary.name}</strong>
                      </div>
                      <span>{beneficiarySubtitle(beneficiary, t)}</span>
                    </div>
                    <div className="beneficiary-actions">
                      <button
                        className={beneficiary.is_favorite ? "button--ghost button--favorite" : "button--ghost"}
                        disabled={actionId === beneficiary.id}
                        onClick={() => toggleFavorite(beneficiary)}
                        type="button"
                      >
                        {beneficiary.is_favorite ? t("payments.favShort") : t("payments.fav")}
                      </button>
                      {beneficiary.phone && (
                        <button
                          className="button--ghost"
                          disabled={actionId === beneficiary.id}
                          onClick={() => {
                            if (beneficiary.iban) {
                              setForm((current) => ({
                                ...current,
                                beneficiary: beneficiary.name,
                                iban: beneficiary.iban ?? "",
                                save_beneficiary: false,
                                is_favorite: false,
                              }));
                              setNotice(t("payments.loadedIntoTransfer", { name: beneficiary.name }));
                              setError(null);
                              setTransferQuote(null);
                            } else {
                              setActiveTab("phone");
                              setPhoneForm((current) => ({ ...current, phone: beneficiary.phone ?? "" }));
                              setPhonePreview(null);
                              setPhoneError(null);
                              setPhoneNotice(null);
                            }
                          }}
                          type="button"
                        >
                          {t("payments.use")}
                        </button>
                      )}
                      {!beneficiary.phone && beneficiary.iban && (
                        <button
                          className="button--ghost"
                          disabled={actionId === beneficiary.id}
                          onClick={() => {
                            setForm((current) => ({
                              ...current,
                              beneficiary: beneficiary.name,
                              iban: beneficiary.iban ?? "",
                              save_beneficiary: false,
                              is_favorite: false,
                            }));
                            setNotice(t("payments.loadedIntoTransfer", { name: beneficiary.name }));
                            setError(null);
                            setTransferQuote(null);
                          }}
                          type="button"
                        >
                          {t("payments.use")}
                        </button>
                      )}
                      <button
                        className="button--danger"
                        disabled={actionId === beneficiary.id}
                        onClick={() => deleteBeneficiary(beneficiary)}
                        type="button"
                      >
                        {t("payments.delete")}
                      </button>
                    </div>
                  </div>
                ))}
                {!loading && beneficiaries.length === 0 && (
                  <div className="empty-state">{t("payments.noBeneficiariesYet")}</div>
                )}
              </div>
            </section>
          </div>
        </div>
      ) : activeTab === "phone" ? (
        <form className="tile phone-transfer-card" onSubmit={handlePhoneTransfer}>
          <label>
            {t("payments.phoneNumber")}
            <div className="phone-lookup-row">
              <input
                onChange={(event) => {
                  setPhoneForm((current) => ({ ...current, phone: event.target.value }));
                  setPhonePreview(null);
                  setPhoneNotice(null);
                }}
                placeholder="+40 741 220 118"
                required
                value={phoneForm.phone}
              />
              <button disabled={phoneLookingUp || !phoneForm.phone.trim()} onClick={handlePhoneLookup} type="button">
                {phoneLookingUp ? t("payments.finding") : t("payments.find")}
              </button>
            </div>
          </label>

          {phonePreview && (
            <div className="match-card">
              <span className="beneficiary-avatar">{initials(`${phonePreview.first_name} ${phonePreview.last_name}`)}</span>
              <div className="beneficiary-meta">
                <strong>
                  {phonePreview.first_name} {phonePreview.last_name}
                </strong>
                <span>{t("payments.walletSuffix", { currency: phonePreview.destination_wallet_currency })}</span>
              </div>
              <span className="tag tag--accent">{t("payments.match")}</span>
            </div>
          )}

          <label>
            {t("payments.payFrom")}
            <select
              disabled={walletsLoading}
              onChange={(event) => setPhoneForm((current) => ({ ...current, source_wallet_id: event.target.value }))}
              required
              value={phoneForm.source_wallet_id}
            >
              {wallets.map((wallet) => (
                <option key={wallet.id} value={wallet.id}>
                  {walletLabel(wallet)}
                </option>
              ))}
            </select>
          </label>

          <label>
            {t("payments.amount")}
            <input
              min="0.01"
              onChange={(event) => setPhoneForm((current) => ({ ...current, amount: event.target.value }))}
              required
              step="0.01"
              type="number"
              value={phoneForm.amount}
            />
          </label>

          <label>
            {t("payments.description")}
            <input
              onChange={(event) => setPhoneForm((current) => ({ ...current, description: event.target.value }))}
              placeholder={t("payments.descriptionPlaceholderPhone")}
              value={phoneForm.description}
            />
          </label>

          {phoneError && <p className="status-line status-line--error">{phoneError}</p>}
          {phoneNotice && <p className="status-line">{phoneNotice}</p>}

          <button
            disabled={phoneSending || !phonePreview || !phoneForm.source_wallet_id || !phoneForm.amount}
            type="submit"
          >
            {phoneSending ? t("payments.sending") : t("payments.sendByPhone")}
          </button>
        </form>
      ) : activeTab === "qr" ? (
        <div className="qr-grid">
          <form className="tile qr-card" onSubmit={handleQrCreate}>
            <div>
              <span className="eyebrow">{t("payments.paymentRequest")}</span>
              <h2>{t("payments.createQrRequest")}</h2>
            </div>

            <label>
              {t("payments.destinationWallet")}
              <select
                disabled={walletsLoading}
                onChange={(event) =>
                  setQrForm((current) => ({ ...current, destination_wallet_id: event.target.value }))
                }
                required
                value={qrForm.destination_wallet_id}
              >
                {wallets.map((wallet) => (
                  <option key={wallet.id} value={wallet.id}>
                    {walletLabel(wallet)}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t("payments.amount")}
              <input
                min="0.01"
                onChange={(event) => setQrForm((current) => ({ ...current, amount: event.target.value }))}
                placeholder={t("payments.optional")}
                step="0.01"
                type="number"
                value={qrForm.amount}
              />
            </label>

            <label>
              {t("payments.expiresInMinutes")}
              <input
                min="1"
                onChange={(event) =>
                  setQrForm((current) => ({ ...current, expires_in_minutes: event.target.value }))
                }
                required
                step="1"
                type="number"
                value={qrForm.expires_in_minutes}
              />
            </label>

            {user?.user_type === "BUSINESS" && (
              <>
                <label>
                  {t("payments.invoiceReference")}
                  <input
                    onChange={(event) => setQrForm((current) => ({ ...current, reference: event.target.value }))}
                    placeholder="INV-0042"
                    value={qrForm.reference}
                  />
                </label>

                <label>
                  {t("payments.invoiceNote")}
                  <input
                    onChange={(event) => setQrForm((current) => ({ ...current, note: event.target.value }))}
                    placeholder={t("payments.optional")}
                    value={qrForm.note}
                  />
                </label>
              </>
            )}

            <button disabled={qrCreating || !qrForm.destination_wallet_id} type="submit">
              {qrCreating ? t("payments.creating") : t("payments.generateRequest")}
            </button>

            {qrRequest && (
              <div className="qr-result">
                <QrCode className="qr-code" value={qrRequest.id} label={t("payments.generatedQrPreview")} />
                <div className="qr-result__details">
                  <span className="eyebrow">{t("payments.requestId")}</span>
                  <code>{qrRequest.id}</code>
                  <span>
                    {t("payments.expiresAt", {
                      amount: qrRequest.amount ?? t("payments.openAmount"),
                      currency: qrRequest.currency,
                      time: new Date(qrRequest.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                    })}
                  </span>
                  {qrRequest.reference && <span>{qrRequest.reference}</span>}
                  {qrRequest.note && <span>{qrRequest.note}</span>}
                </div>
                <button
                  type="button"
                  className="button--ghost qr-result__download"
                  onClick={() => downloadQrPng(qrRequest.id, `payment-request-${qrRequest.id}.png`)}
                  title={t("payments.downloadQr")}
                >
                  <Download size={14} aria-hidden="true" />
                  {t("payments.downloadQr")}
                </button>
              </div>
            )}
          </form>

          <form className="tile qr-card" onSubmit={handleQrPay}>
            <div>
              <span className="eyebrow">{t("payments.scanOrPaste")}</span>
              <h2>{t("payments.payQrRequest")}</h2>
            </div>

            <label>
              {t("payments.requestId")}
              <div className="phone-lookup-row">
                <input
                  onChange={(event) => {
                    setQrPayForm((current) => ({ ...current, request_id: event.target.value }));
                    setQrLookup(null);
                    setQrNotice(null);
                  }}
                  required
                  value={qrPayForm.request_id}
                />
                <button
                  disabled={qrLookingUp || !qrPayForm.request_id.trim()}
                  onClick={handleQrLookup}
                  type="button"
                >
                  {qrLookingUp ? t("payments.loadingButton") : t("payments.load")}
                </button>
              </div>
            </label>

            {qrLookup && (
              <div className="request-summary">
                <span className="eyebrow">{t("payments.activeRequest")}</span>
                <strong>
                  {qrLookup.amount ?? t("payments.openAmount")} {qrLookup.currency}
                </strong>
                <span>{t("payments.expiresOn", { date: new Date(qrLookup.expires_at).toLocaleString() })}</span>
              </div>
            )}

            <label>
              {t("payments.payFrom")}
              <select
                disabled={walletsLoading}
                onChange={(event) => setQrPayForm((current) => ({ ...current, source_wallet_id: event.target.value }))}
                required
                value={qrPayForm.source_wallet_id}
              >
                {wallets.map((wallet) => (
                  <option key={wallet.id} value={wallet.id}>
                    {walletLabel(wallet)}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t("payments.amount")}
              <input
                disabled={Boolean(qrLookup?.amount)}
                min="0.01"
                onChange={(event) => setQrPayForm((current) => ({ ...current, amount: event.target.value }))}
                placeholder={qrLookup?.amount ?? t("payments.requiredForOpenRequests")}
                required={!qrLookup?.amount}
                step="0.01"
                type="number"
                value={qrLookup?.amount ?? qrPayForm.amount}
              />
            </label>

            {qrError && <p className="status-line status-line--error">{qrError}</p>}
            {qrNotice && <p className="status-line">{qrNotice}</p>}

            <button
              disabled={
                qrPaying ||
                !qrPayForm.request_id.trim() ||
                !qrPayForm.source_wallet_id ||
                (!qrLookup?.amount && !qrPayForm.amount)
              }
              type="submit"
            >
              {qrPaying ? t("payments.paying") : t("payments.payRequest")}
            </button>
          </form>
        </div>
      ) : activeTab === "scheduled" ? (
        <div className="scheduled-grid">
          <form className="tile scheduled-form-card" onSubmit={handleScheduledSubmit}>
            <div>
              <span className="eyebrow">{t("payments.newScheduledPayment")}</span>
              <h2>{t("payments.createSchedule")}</h2>
            </div>

            <label>
              {t("payments.payee")}
              <input
                onChange={(event) =>
                  setScheduledForm((current) => ({ ...current, beneficiary_name: event.target.value }))
                }
                required
                value={scheduledForm.beneficiary_name}
              />
            </label>

            <label>
              {t("payments.iban")}
              <input
                onChange={(event) => setScheduledForm((current) => ({ ...current, iban: event.target.value }))}
                placeholder="RO49 AAAA 1B31 0075 9384 0000"
                required
                value={scheduledForm.iban}
              />
            </label>

            <label>
              {t("payments.payFrom")}
              <select
                disabled={walletsLoading}
                onChange={(event) => {
                  const wallet = wallets.find((item) => item.id === event.target.value);
                  setScheduledForm((current) => ({
                    ...current,
                    source_wallet_id: event.target.value,
                    currency: wallet?.currency ?? current.currency,
                  }));
                }}
                required
                value={scheduledForm.source_wallet_id}
              >
                {wallets.map((wallet) => (
                  <option key={wallet.id} value={wallet.id}>
                    {walletLabel(wallet)}
                  </option>
                ))}
              </select>
            </label>

            <div className="amount-row">
              <label>
                {t("payments.amount")}
                <input
                  min="0.01"
                  onChange={(event) => setScheduledForm((current) => ({ ...current, amount: event.target.value }))}
                  required
                  step="0.01"
                  type="number"
                  value={scheduledForm.amount}
                />
              </label>
              <label>
                {t("payments.currency")}
                <select
                  onChange={(event) => setScheduledForm((current) => ({ ...current, currency: event.target.value }))}
                  required
                  value={scheduledForm.currency}
                >
                  {(transferCurrencies.length > 0 ? transferCurrencies : ["RON"]).map((currency) => (
                    <option key={currency} value={currency}>
                      {currency}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="scheduled-controls">
              <label>
                {t("payments.frequency")}
                <select
                  onChange={(event) =>
                    setScheduledForm((current) => ({
                      ...current,
                      frequency: event.target.value as ScheduledPaymentFrequency,
                    }))
                  }
                  value={scheduledForm.frequency}
                >
                  {SCHEDULED_FREQUENCIES.map((frequency) => (
                    <option key={frequency} value={frequency}>
                      {t(`payments.frequencyOption.${frequency}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("payments.nextRun")}
                <input
                  min={new Date().toISOString().slice(0, 10)}
                  onChange={(event) => setScheduledForm((current) => ({ ...current, next_run_on: event.target.value }))}
                  required
                  type="date"
                  value={scheduledForm.next_run_on}
                />
              </label>
              <label>
                {t("payments.notify")}
                <input
                  min="0"
                  max="30"
                  onChange={(event) =>
                    setScheduledForm((current) => ({ ...current, notify_days_before: event.target.value }))
                  }
                  required
                  step="1"
                  type="number"
                  value={scheduledForm.notify_days_before}
                />
              </label>
            </div>

            <label>
              {t("payments.description")}
              <input
                onChange={(event) => setScheduledForm((current) => ({ ...current, description: event.target.value }))}
                placeholder={t("payments.electricityBillPlaceholder")}
                value={scheduledForm.description}
              />
            </label>

            {hasScheduledCurrencyMismatch && (
              <p className="status-line status-line--error">
                {t("payments.scheduledCurrencyMismatch")}
              </p>
            )}
            {scheduledError && <p className="status-line status-line--error">{scheduledError}</p>}
            {scheduledNotice && <p className="status-line">{scheduledNotice}</p>}

            <button
              disabled={
                scheduledSubmitting ||
                hasScheduledCurrencyMismatch ||
                !scheduledForm.source_wallet_id
              }
              type="submit"
            >
              {scheduledSubmitting ? t("payments.creating") : t("payments.createScheduledPayment")}
            </button>
          </form>

          <section className="tile scheduled-list-card">
            <div className="tile__header">
              <span className="eyebrow">{t("payments.scheduledPayments")}</span>
              {scheduledLoading && <span className="tag tag--neutral">{t("payments.loading")}</span>}
            </div>

            <div className="scheduled-table">
              <div className="scheduled-row scheduled-row--head">
                <span>{t("payments.payee")}</span>
                <span>{t("payments.frequency")}</span>
                <span>{t("payments.nextRun")}</span>
                <span>{t("payments.notify")}</span>
                <span>{t("payments.amount")}</span>
                <span>{t("common.statusLabel")}</span>
                <span />
              </div>
              {scheduledPayments.map((payment) => (
                <div className="scheduled-row" key={payment.id}>
                  <strong>{payment.beneficiary_name}</strong>
                  <span>{t(`payments.frequencyOption.${payment.frequency}`)}</span>
                  <span>{new Date(`${payment.next_run_on}T00:00:00`).toLocaleDateString()}</span>
                  <span>{t("payments.daysBefore", { days: payment.notify_days_before })}</span>
                  <strong>
                    {payment.amount} {payment.currency}
                  </strong>
                  <span className={`tag scheduled-status scheduled-status--${payment.status.toLowerCase()}`}>
                    {t(`payments.scheduledStatusBadge.${payment.status.toLowerCase()}`, { defaultValue: payment.status })}
                  </span>
                  <div className="beneficiary-actions scheduled-actions">
                    {payment.status === "ACTIVE" && (
                      <button
                        className="button--ghost"
                        disabled={scheduledActionId === payment.id}
                        onClick={() => updateScheduledStatus(payment, "PAUSED")}
                        type="button"
                      >
                        {t("payments.pause")}
                      </button>
                    )}
                    {payment.status === "PAUSED" && (
                      <button
                        className="button--ghost"
                        disabled={scheduledActionId === payment.id}
                        onClick={() => updateScheduledStatus(payment, "ACTIVE")}
                        type="button"
                      >
                        {t("payments.resume")}
                      </button>
                    )}
                    {payment.status !== "CANCELLED" && (
                      <button
                        className="button--danger"
                        disabled={scheduledActionId === payment.id}
                        onClick={() => updateScheduledStatus(payment, "CANCELLED")}
                        type="button"
                      >
                        {t("payments.cancel")}
                      </button>
                    )}
                    <button
                      className="button--danger"
                      disabled={scheduledActionId === payment.id}
                      onClick={() => deleteScheduledPayment(payment)}
                      type="button"
                    >
                      {t("payments.delete")}
                    </button>
                  </div>
                </div>
              ))}
              {!scheduledLoading && scheduledPayments.length === 0 && (
                <div className="empty-state">{t("payments.noScheduledPaymentsYet")}</div>
              )}
            </div>
          </section>

          <ScheduledPaymentsCalendar payments={scheduledPayments} />
        </div>
      ) : activeTab === "folders" ? (
        <div className="folder-view-grid">
          <section className="tile scheduled-list-card">
            <div className="tile__header">
              <span className="eyebrow">{t("payments.transactionFolders")}</span>
              {folderLoading && <span className="tag tag--neutral">{t("payments.loading")}</span>}
            </div>

            {folderError && <div className="form-error">{folderError}</div>}

            <div className="folder-readonly-list">
              {transactionFolders.map((folder) => {
                const data = folderSplitData(folder);
                const splitButtonLabel =
                  data.split?.status === "SETTLED"
                    ? t("payments.splitted")
                    : data.hasDeclinedSplit
                      ? t("payments.splitAgain")
                    : data.split?.status === "OPEN"
                      ? t("payments.waitingPayments")
                      : t("payments.splitFolder");
                const hasActiveFolderSplit =
                  data.split?.status === "SETTLED" || (data.split?.status === "OPEN" && !data.hasDeclinedSplit);
                const splitDisabled =
                  hasActiveFolderSplit ||
                  data.transactions.length === 0 ||
                  data.hasMixedCurrencies ||
                  folderActionId === folder.id;
                return (
                  <div
                    className={
                      highlightedFolderId === folder.id
                        ? "folder-readonly-card folder-readonly-card--active"
                        : "folder-readonly-card"
                    }
                    key={folder.id}
                  >
                    <div className="folder-readonly-card__header">
                      <div className="folder-readonly-card__meta">
                        <div className="folder-readonly-card__title">
                          <strong>{folder.name}</strong>
                          {data.currency && <span className="tag tag--outline">{data.total} {data.currency}</span>}
                        </div>
                        <span>{folder.description || t("payments.noDescription")}</span>
                      </div>
                      <div className="folder-readonly-card__actions">
                        <button
                          className="button--ghost"
                          disabled={splitDisabled}
                          onClick={() => openFolderSplit(folder)}
                          type="button"
                        >
                          {folderActionId === folder.id && !data.split ? t("payments.working") : splitButtonLabel}
                        </button>
                        {data.split?.status === "OPEN" && (
                          <button
                            className="button--danger"
                            disabled={splitActionId === data.split.id}
                            onClick={() => data.split && cancelBillSplit(data.split)}
                            type="button"
                          >
                            {splitActionId === data.split.id ? t("payments.cancelling") : t("payments.cancelSplit")}
                          </button>
                        )}
                        <button
                          className="button--danger"
                          disabled={folderActionId === folder.id}
                          onClick={() => deleteTransactionFolder(folder)}
                          type="button"
                        >
                          {t("payments.delete")}
                        </button>
                      </div>
                    </div>
                    {data.hasMixedCurrencies && (
                      <p className="status-line status-line--error">{t("payments.mixedCurrencyCannotSplit")}</p>
                    )}
                    {data.hasDeclinedSplit && (
                      <p className="status-line status-line--error">{t("payments.participantRefused")}</p>
                    )}
                    {data.split?.status === "SETTLED" && (
                      <p className="status-line">
                        {t("payments.alreadySettled")}
                      </p>
                    )}
                    <div className="folder-readonly-card__items">
                      {folder.items.map((item) => {
                        const transaction = transactions.find((candidate) => candidate.id === item.transaction_id);
                        return (
                          <div className="folder-transaction-row" key={item.id}>
                            <div>
                              <span>{transaction?.description || transaction?.type || item.transaction_id}</span>
                              <strong>{transaction ? `${transaction.amount} ${transaction.currency}` : t("payments.transactionFallback")}</strong>
                            </div>
                            <button
                              className="button--danger"
                              disabled={folderActionId === item.transaction_id}
                              onClick={() => removeTransactionFromFolder(folder, item.transaction_id)}
                              type="button"
                            >
                              {t("payments.remove")}
                            </button>
                          </div>
                        );
                      })}
                      {folder.items.length === 0 && <div className="empty-state">{t("payments.noTransactionsInFolder")}</div>}
                    </div>
                  </div>
                );
              })}
              {!folderLoading && transactionFolders.length === 0 && (
                <div className="empty-state">{t("payments.noFoldersYet")}</div>
              )}
            </div>
          </section>
        </div>
      ) : (
        <section className="tile tab-panel-placeholder">
          <span className="eyebrow">{TABS.find((tab) => tab.id === activeTab)?.labelKey ? t(TABS.find((tab) => tab.id === activeTab)!.labelKey) : ""}</span>
          <p>{t("payments.nextDeveloperNote")}</p>
        </section>
      )}

      {folderSplitTarget ? (
        <div className="folder-modal-backdrop" role="presentation">
          <form className="tile folder-modal" onSubmit={createFolderBillSplit} role="dialog" aria-modal="true">
            <div className="tile__header">
              <div>
                <span className="eyebrow">{t("payments.splitFolderTitle")}</span>
                <h2>{folderSplitTarget.name}</h2>
              </div>
              <button className="button--ghost" onClick={() => setFolderSplitTarget(null)} type="button">
                {t("payments.close")}
              </button>
            </div>

            <div className="split-builder__summary">
              <strong>
                {folderSplitData(folderSplitTarget).total} {folderSplitData(folderSplitTarget).currency || t("payments.mixed")}
              </strong>
              <span>{t("payments.transactionCount", { count: folderSplitTarget.items.length })}</span>
              <button className="button--ghost button--wide" onClick={splitFolderEqually} type="button">
                {t("payments.splitEqually")}
              </button>
            </div>

            <div className="folder-modal__list">
              {folderSplitExceedsTotal && (
                <p className="status-line status-line--error">
                  {t("payments.splitExceedsPercent", { percent: folderSplitPercentTotal.toFixed(2) })}
                </p>
              )}
              {folderSplitParticipants.map((participant) => {
                const total = Number(folderSplitData(folderSplitTarget).total);
                const share = ((total * Number(participant.percent || 0)) / 100).toFixed(2);
                return (
                  <div className="folder-split-participant" key={participant.key}>
                    <label>
                      {t("payments.recipientName")}
                      <input
                        onChange={(event) =>
                          updateFolderSplitParticipant(participant.key, { name: event.target.value })
                        }
                        placeholder="Maria Dinu"
                        required
                        value={participant.name}
                      />
                    </label>
                    <label>
                      {t("payments.phoneNumber")}
                      <input
                        onChange={(event) =>
                          updateFolderSplitParticipant(participant.key, { phone: event.target.value })
                        }
                        placeholder="+40700000003"
                        required
                        value={participant.phone}
                      />
                    </label>
                    <label>
                      {t("payments.percent")}
                      <input
                        max="100"
                        min="0.01"
                        onChange={(event) =>
                          updateFolderSplitParticipant(participant.key, { percent: event.target.value })
                        }
                        required
                        step="0.01"
                        type="number"
                        value={participant.percent}
                      />
                    </label>
                    <div className="folder-split-participant__amount">
                      <strong>
                        {share} {folderSplitData(folderSplitTarget).currency || ""}
                      </strong>
                      <span>{normalizePhone(participant.phone) || t("payments.phoneRequired")}</span>
                    </div>
                    <button
                      className="button--danger"
                      onClick={() => removeFolderSplitParticipant(participant.key)}
                      type="button"
                    >
                      {t("payments.remove")}
                    </button>
                  </div>
                );
              })}
              {folderSplitParticipants.length === 0 && (
                <div className="empty-state">{t("payments.addPeopleToSplit")}</div>
              )}
            </div>

            {folderError && <p className="status-line status-line--error">{folderError}</p>}

            <div className="beneficiary-actions">
              <button className="button--ghost button--wide" onClick={addFolderSplitParticipant} type="button">
                {t("payments.addPerson")}
              </button>
              <button
                className="button--wide"
                disabled={folderActionId === folderSplitTarget.id || folderSplitExceedsTotal}
                type="submit"
              >
                {folderActionId === folderSplitTarget.id ? t("payments.creating") : t("payments.sendFolderSplit")}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function daysInMonth(year: number, monthIndex: number): number {
  return new Date(year, monthIndex + 1, 0).getDate();
}

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** True when `date` falls on a same-day-of-month cadence `intervalMonths`
 * apart from `start` — clamped to the shorter month's length (e.g. a 31st
 * start still lands on Feb 28/29). */
function matchesMonthlyInterval(date: Date, start: Date, intervalMonths: number): boolean {
  const monthDiff = (date.getFullYear() - start.getFullYear()) * 12 + (date.getMonth() - start.getMonth());
  if (monthDiff < 0 || monthDiff % intervalMonths !== 0) return false;
  const expectedDay = Math.min(start.getDate(), daysInMonth(date.getFullYear(), date.getMonth()));
  return date.getDate() === expectedDay;
}

function occursOnDate(payment: ScheduledPayment, date: Date): boolean {
  if (payment.status !== "ACTIVE") return false;
  const start = new Date(`${payment.next_run_on}T00:00:00`);
  if (date < start) return false;
  switch (payment.frequency) {
    case "ONCE":
      return sameDay(date, start);
    case "WEEKLY": {
      const diffDays = Math.round((date.getTime() - start.getTime()) / 86_400_000);
      return diffDays % 7 === 0;
    }
    case "MONTHLY":
      return matchesMonthlyInterval(date, start, 1);
    case "QUARTERLY":
      return matchesMonthlyInterval(date, start, 3);
    case "YEARLY":
      return matchesMonthlyInterval(date, start, 12);
    default:
      return false;
  }
}

/** Upcoming-payments calendar for the "scheduled" tab. Projects each ACTIVE
 * scheduled payment's future occurrences from its frequency — the backend
 * only stores next_run_on (the single next occurrence), so recurring dates
 * beyond that are computed here, read-only, for display purposes only. */
function ScheduledPaymentsCalendar({ payments }: { payments: ScheduledPayment[] }) {
  const { t, i18n } = useTranslation();
  const [viewDate, setViewDate] = useState(() => new Date());
  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const today = new Date();

  const occurrencesByDay = useMemo(() => {
    const map = new Map<number, ScheduledPayment[]>();
    const total = daysInMonth(year, month);
    for (let day = 1; day <= total; day++) {
      const date = new Date(year, month, day);
      const matches = payments.filter((payment) => occursOnDate(payment, date));
      if (matches.length > 0) map.set(day, matches);
    }
    return map;
  }, [payments, year, month]);

  const totalDays = daysInMonth(year, month);
  const leadingBlanks = (new Date(year, month, 1).getDay() + 6) % 7;
  const cells: (number | null)[] = [
    ...Array.from({ length: leadingBlanks }, () => null),
    ...Array.from({ length: totalDays }, (_, index) => index + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const weekdayFormatter = new Intl.DateTimeFormat(i18n.language, { weekday: "short" });
  // 2024-01-01 was a Monday — used purely as a Monday-first reference date.
  const weekdayLabels = Array.from({ length: 7 }, (_, index) =>
    weekdayFormatter.format(new Date(2024, 0, 1 + index)),
  );
  const isViewingCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

  return (
    <section className="tile scheduled-calendar-card">
      <div className="tile__header">
        <span className="eyebrow">{t("payments.calendarTitle")}</span>
        <div className="scheduled-calendar-nav">
          <button
            aria-label={t("payments.calendarPrevMonth")}
            className="button--ghost"
            onClick={() => setViewDate(new Date(year, month - 1, 1))}
            type="button"
          >
            ‹
          </button>
          <strong>{viewDate.toLocaleDateString(i18n.language, { month: "long", year: "numeric" })}</strong>
          <button
            aria-label={t("payments.calendarNextMonth")}
            className="button--ghost"
            onClick={() => setViewDate(new Date(year, month + 1, 1))}
            type="button"
          >
            ›
          </button>
        </div>
      </div>

      <div className="scheduled-calendar-grid">
        {weekdayLabels.map((label, index) => (
          <div className="scheduled-calendar-weekday" key={`${label}-${index}`}>
            {label}
          </div>
        ))}
        {cells.map((day, index) => {
          const matches = day ? occurrencesByDay.get(day) ?? [] : [];
          const isToday = isViewingCurrentMonth && day === today.getDate();
          const classes = [
            "scheduled-calendar-day",
            day ? "" : "scheduled-calendar-day--empty",
            isToday ? "scheduled-calendar-day--today" : "",
            matches.length > 0 ? "scheduled-calendar-day--has-payments" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <div className={classes} key={index}>
              {day && (
                <>
                  <span className="scheduled-calendar-day__number">{day}</span>
                  <div className="scheduled-calendar-day__items">
                    {matches.slice(0, 2).map((payment) => (
                      <span
                        className="scheduled-calendar-day__item"
                        key={payment.id}
                        title={`${payment.beneficiary_name} · ${payment.amount} ${payment.currency}`}
                      >
                        {payment.beneficiary_name}
                      </span>
                    ))}
                    {matches.length > 2 && (
                      <span className="scheduled-calendar-day__more">
                        {t("payments.calendarMore", { count: matches.length - 2 })}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {occurrencesByDay.size === 0 && <div className="empty-state">{t("payments.calendarEmptyMonth")}</div>}
    </section>
  );
}

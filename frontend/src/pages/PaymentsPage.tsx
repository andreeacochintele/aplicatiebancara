import { useEffect, useState, type FormEvent } from "react";

import { ApiError, apiRequest } from "../api/apiClient";
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

type PaymentTab = "transfer" | "phone" | "qr" | "scheduled" | "split" | "folders";

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

interface BillSplitFormState {
  title: string;
  total_amount: string;
  currency: string;
  participant_user_id: string;
  participant_name: string;
  participant_phone: string;
  participant_amount: string;
  source_transaction_id: string;
  description: string;
}

interface FolderFormState {
  name: string;
  color: string;
  description: string;
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

const EMPTY_BILL_SPLIT_FORM: BillSplitFormState = {
  title: "",
  total_amount: "",
  currency: "RON",
  participant_user_id: "",
  participant_name: "",
  participant_phone: "",
  participant_amount: "",
  source_transaction_id: "",
  description: "",
};

const EMPTY_FOLDER_FORM: FolderFormState = {
  name: "",
  color: "violet",
  description: "",
};

const TABS: Array<{ id: PaymentTab; label: string }> = [
  { id: "transfer", label: "Transfer" },
  { id: "phone", label: "By phone" },
  { id: "qr", label: "QR request" },
  { id: "scheduled", label: "Scheduled" },
  { id: "split", label: "Split bill" },
  { id: "folders", label: "Folders" },
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

function beneficiarySubtitle(beneficiary: Beneficiary): string {
  const details = [beneficiary.iban, beneficiary.phone].filter(Boolean);
  return details.length > 0 ? details.join(" - ") : "Internal beneficiary";
}

function walletLabel(wallet: Wallet): string {
  return `${wallet.currency} - ${wallet.available_balance}`;
}

function walletCurrency(wallets: Wallet[], walletId: string): string {
  return wallets.find((wallet) => wallet.id === walletId)?.currency ?? "RON";
}

function normalizePhone(value: string): string {
  return value.replace(/\s/g, "");
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
  const { accessToken, user } = useAuth();
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
  const [billSplitForm, setBillSplitForm] = useState<BillSplitFormState>(EMPTY_BILL_SPLIT_FORM);
  const [folderForm, setFolderForm] = useState<FolderFormState>(EMPTY_FOLDER_FORM);
  const [folderTransactionId, setFolderTransactionId] = useState("");
  const [qrRequest, setQrRequest] = useState<PaymentRequest | null>(null);
  const [qrLookup, setQrLookup] = useState<PaymentRequest | null>(null);
  const [scheduledPayments, setScheduledPayments] = useState<ScheduledPayment[]>([]);
  const [billSplits, setBillSplits] = useState<BillSplit[]>([]);
  const [transactionFolders, setTransactionFolders] = useState<TransactionFolder[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [transferQuote, setTransferQuote] = useState<FXQuote | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);
  const [qrNotice, setQrNotice] = useState<string | null>(null);
  const [scheduledError, setScheduledError] = useState<string | null>(null);
  const [scheduledNotice, setScheduledNotice] = useState<string | null>(null);
  const [splitError, setSplitError] = useState<string | null>(null);
  const [splitNotice, setSplitNotice] = useState<string | null>(null);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [folderNotice, setFolderNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [walletsLoading, setWalletsLoading] = useState(false);
  const [phoneLookingUp, setPhoneLookingUp] = useState(false);
  const [phoneSending, setPhoneSending] = useState(false);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [scheduledLoading, setScheduledLoading] = useState(false);
  const [scheduledSubmitting, setScheduledSubmitting] = useState(false);
  const [splitLoading, setSplitLoading] = useState(false);
  const [splitSubmitting, setSplitSubmitting] = useState(false);
  const [folderLoading, setFolderLoading] = useState(false);
  const [folderSubmitting, setFolderSubmitting] = useState(false);
  const [qrCreating, setQrCreating] = useState(false);
  const [qrLookingUp, setQrLookingUp] = useState(false);
  const [qrPaying, setQrPaying] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [scheduledActionId, setScheduledActionId] = useState<string | null>(null);
  const [splitActionId, setSplitActionId] = useState<string | null>(null);
  const [folderActionId, setFolderActionId] = useState<string | null>(null);

  async function loadBeneficiaries() {
    if (!accessToken) return;
    setLoading(true);
    try {
      const list = await apiRequest<Beneficiary[]>("/payments/beneficiaries", { token: accessToken });
      setBeneficiaries(sortBeneficiaries(list));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load beneficiaries");
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
      setPhoneError(err instanceof ApiError ? err.message : "Could not load wallets");
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

  async function loadScheduledPayments() {
    if (!accessToken) return;
    setScheduledLoading(true);
    try {
      const list = await apiRequest<ScheduledPayment[]>("/payments/scheduled-payments", { token: accessToken });
      setScheduledPayments(list);
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : "Could not load scheduled payments");
    } finally {
      setScheduledLoading(false);
    }
  }

  async function loadBillSplits() {
    if (!accessToken) return;
    setSplitLoading(true);
    try {
      const list = await apiRequest<BillSplit[]>("/payments/bill-splits", { token: accessToken });
      setBillSplits(list);
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not load bill splits");
    } finally {
      setSplitLoading(false);
    }
  }

  async function loadTransactionFolders() {
    if (!accessToken) return;
    setFolderLoading(true);
    try {
      const list = await apiRequest<TransactionFolder[]>("/payments/transaction-folders", { token: accessToken });
      setTransactionFolders(list);
      setSelectedFolderId((current) => current || list[0]?.id || "");
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : "Could not load transaction folders");
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
      setNotice("FX quote ready. Review it, then accept to send.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create FX quote");
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
      setNotice(`Transfer completed: ${transaction.amount} ${transaction.currency}`);
      resetForm();
      await loadWallets();
      await loadBeneficiaries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not complete transfer");
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
      setError(err instanceof ApiError ? err.message : "Could not update favorite");
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
      setNotice("Beneficiary deleted.");
      await loadBeneficiaries();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete beneficiary");
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
        setPhoneError(`${saved.name} is saved as a beneficiary, but is not linked to an in-app wallet yet.`);
      } else {
        setPhoneError(err instanceof ApiError ? err.message : "Could not find this phone number");
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
      setPhoneNotice(`Transfer completed: ${transaction.amount} ${transaction.currency}`);
      setPhoneForm((current) => ({ ...current, amount: "", description: "" }));
      await loadWallets();
    } catch (err) {
      setPhoneError(err instanceof ApiError ? err.message : "Could not complete transfer");
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
        },
      });
      setQrRequest(paymentRequest);
      setQrPayForm((current) => ({ ...current, request_id: paymentRequest.id }));
      setQrNotice("Payment request created.");
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : "Could not create payment request");
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
      setQrError(err instanceof ApiError ? err.message : "Could not load payment request");
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
          description: "QR payment",
        },
      });
      setQrNotice(`QR payment completed: ${transaction.amount} ${transaction.currency}`);
      setQrLookup(null);
      setQrPayForm((current) => ({ ...current, amount: "" }));
      await loadWallets();
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : "Could not pay payment request");
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
      setScheduledNotice("Scheduled payment created.");
      resetScheduledForm();
      await loadScheduledPayments();
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : "Could not create scheduled payment");
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
      setScheduledNotice(`Scheduled payment ${status.toLowerCase()}.`);
      await loadScheduledPayments();
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : "Could not update scheduled payment");
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
      setScheduledNotice("Scheduled payment deleted.");
      await loadScheduledPayments();
    } catch (err) {
      setScheduledError(err instanceof ApiError ? err.message : "Could not delete scheduled payment");
    } finally {
      setScheduledActionId(null);
    }
  }

  async function handleBillSplitSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setSplitSubmitting(true);
    setSplitError(null);
    setSplitNotice(null);
    try {
      await apiRequest<BillSplit>("/payments/bill-splits", {
        method: "POST",
        token: accessToken,
        body: {
          title: billSplitForm.title.trim(),
          total_amount: billSplitForm.total_amount,
          currency: billSplitForm.currency,
          source_transaction_id: compact(billSplitForm.source_transaction_id),
          description: compact(billSplitForm.description),
          participants: [
            {
              participant_user_id: compact(billSplitForm.participant_user_id),
              name: billSplitForm.participant_name.trim(),
              phone: compact(billSplitForm.participant_phone),
              amount: billSplitForm.participant_amount,
            },
          ],
        },
      });
      setSplitNotice("Bill split created.");
      setBillSplitForm((current) => ({
        ...EMPTY_BILL_SPLIT_FORM,
        currency: current.currency,
      }));
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not create bill split");
    } finally {
      setSplitSubmitting(false);
    }
  }

  async function cancelBillSplit(split: BillSplit) {
    if (!accessToken) return;
    setSplitActionId(split.id);
    setSplitError(null);
    setSplitNotice(null);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/cancel`, {
        method: "PATCH",
        token: accessToken,
      });
      setSplitNotice("Bill split cancelled.");
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not cancel bill split");
    } finally {
      setSplitActionId(null);
    }
  }

  async function payBillSplit(split: BillSplit, participantId: string) {
    if (!accessToken) return;
    const sourceWallet = wallets.find((wallet) => wallet.currency === split.currency);
    if (!sourceWallet) {
      setSplitError(`No ${split.currency} wallet available for this payment.`);
      return;
    }
    setSplitActionId(participantId);
    setSplitError(null);
    setSplitNotice(null);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/participants/${participantId}/pay`, {
        method: "POST",
        token: accessToken,
        body: { source_wallet_id: sourceWallet.id },
      });
      setSplitNotice("Bill split participant paid.");
      await loadBillSplits();
      await loadWallets();
      await loadTransactions();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not pay bill split");
    } finally {
      setSplitActionId(null);
    }
  }

  async function handleFolderSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setFolderSubmitting(true);
    setFolderError(null);
    setFolderNotice(null);
    try {
      const folder = await apiRequest<TransactionFolder>("/payments/transaction-folders", {
        method: "POST",
        token: accessToken,
        body: {
          name: folderForm.name.trim(),
          color: compact(folderForm.color),
          description: compact(folderForm.description),
        },
      });
      setFolderNotice("Transaction folder created.");
      setFolderForm(EMPTY_FOLDER_FORM);
      setSelectedFolderId(folder.id);
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : "Could not create transaction folder");
    } finally {
      setFolderSubmitting(false);
    }
  }

  async function deleteTransactionFolder(folder: TransactionFolder) {
    if (!accessToken) return;
    setFolderActionId(folder.id);
    setFolderError(null);
    setFolderNotice(null);
    try {
      await apiRequest<void>(`/payments/transaction-folders/${folder.id}`, {
        method: "DELETE",
        token: accessToken,
      });
      setFolderNotice("Transaction folder deleted.");
      setSelectedFolderId("");
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : "Could not delete transaction folder");
    } finally {
      setFolderActionId(null);
    }
  }

  async function addTransactionToFolder(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || !selectedFolderId || !folderTransactionId) return;
    setFolderActionId(folderTransactionId);
    setFolderError(null);
    setFolderNotice(null);
    try {
      await apiRequest<TransactionFolder>(`/payments/transaction-folders/${selectedFolderId}/transactions`, {
        method: "POST",
        token: accessToken,
        body: { transaction_id: folderTransactionId },
      });
      setFolderNotice("Transaction added to folder.");
      setFolderTransactionId("");
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : "Could not add transaction to folder");
    } finally {
      setFolderActionId(null);
    }
  }

  async function removeTransactionFromFolder(folderId: string, transactionId: string) {
    if (!accessToken) return;
    setFolderActionId(transactionId);
    setFolderError(null);
    setFolderNotice(null);
    try {
      await apiRequest<void>(`/payments/transaction-folders/${folderId}/transactions/${transactionId}`, {
        method: "DELETE",
        token: accessToken,
      });
      setFolderNotice("Transaction removed from folder.");
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : "Could not remove transaction from folder");
    } finally {
      setFolderActionId(null);
    }
  }

  const transferWallet = wallets.find((wallet) => wallet.id === form.source_wallet_id);
  const transferCurrencies = Array.from(new Set(wallets.map((wallet) => wallet.currency)));
  const hasTransferCurrencyMismatch = Boolean(transferWallet && transferWallet.currency !== form.currency);
  const scheduledWallet = wallets.find((wallet) => wallet.id === scheduledForm.source_wallet_id);
  const hasScheduledCurrencyMismatch = Boolean(scheduledWallet && scheduledWallet.currency !== scheduledForm.currency);
  const selectedFolder = transactionFolders.find((folder) => folder.id === selectedFolderId) ?? transactionFolders[0];
  const selectedFolderItemIds = new Set(selectedFolder?.items.map((item) => item.transaction_id) ?? []);
  const folderCandidateTransactions = transactions.filter((transaction) => !selectedFolderItemIds.has(transaction.id));
  const internalBeneficiaries = beneficiaries.filter((beneficiary) => beneficiary.beneficiary_user_id);

  return (
    <section className="payments-page">
      <div className="payment-tabs" role="tablist" aria-label="Payment flows">
        {TABS.map((tab) => (
          <button
            className={activeTab === tab.id ? "payment-tabs__button active" : "payment-tabs__button"}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "transfer" ? (
        <div className="payments-grid">
          <form className="tile transfer-form-card" onSubmit={handleIbanTransfer}>
            <div>
              <span className="eyebrow">Details</span>
              <h2>New transfer</h2>
            </div>

            <label>
              Beneficiary
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
              IBAN
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
                Amount
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
                Currency
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
              Pay from
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
              Description
              <input
                onChange={(event) => {
                  setForm((current) => ({ ...current, description: event.target.value }));
                  clearTransferQuote();
                }}
                placeholder="Rent August"
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
              Save beneficiary
            </label>

            {form.save_beneficiary && (
              <label className="checkbox-row">
                <input
                  checked={form.is_favorite}
                  onChange={(event) => setForm((current) => ({ ...current, is_favorite: event.target.checked }))}
                  type="checkbox"
                />
                Favorite
              </label>
            )}

            {hasTransferCurrencyMismatch && transferWallet && !transferQuote && (
              <p className="status-line">
                FX quote required. Your {transferWallet.currency} wallet will be debited after you accept the quote.
              </p>
            )}

            {transferQuote && (
              <div className="fx-quote-card">
                <span className="eyebrow">FX quote</span>
                <div className="quote-row">
                  <span>Debit</span>
                  <strong>
                    {transferQuote.source_amount} {transferQuote.source_currency}
                  </strong>
                </div>
                <div className="quote-row">
                  <span>Recipient receives</span>
                  <strong>
                    {transferQuote.target_amount} {transferQuote.target_currency}
                  </strong>
                </div>
                <div className="quote-row">
                  <span>Rate</span>
                  <strong>{transferQuote.exchange_rate}</strong>
                </div>
                <div className="quote-row">
                  <span>Fee</span>
                  <strong>
                    {transferQuote.fee} {transferQuote.source_currency}
                  </strong>
                </div>
                <span className="quote-expiry">Expires {new Date(transferQuote.expires_at).toLocaleTimeString()}</span>
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
                  ? "Sending..."
                  : quoteLoading
                    ? "Getting quote..."
                    : hasTransferCurrencyMismatch && !transferQuote
                      ? "Get FX quote"
                      : hasTransferCurrencyMismatch
                        ? "Accept quote and send"
                        : form.save_beneficiary
                          ? "Send and save"
                          : "Send transfer"}
              </button>
              <button className="button--ghost" onClick={resetForm} type="button">
                Clear
              </button>
            </div>
          </form>

          <div className="payments-side">
            <section className="tile saved-beneficiaries">
              <div className="tile__header">
                <span className="eyebrow">Saved beneficiaries</span>
                {loading && <span className="tag tag--neutral">Loading</span>}
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
                      <span>{beneficiarySubtitle(beneficiary)}</span>
                    </div>
                    <div className="beneficiary-actions">
                      <button
                        className={beneficiary.is_favorite ? "button--ghost button--favorite" : "button--ghost"}
                        disabled={actionId === beneficiary.id}
                        onClick={() => toggleFavorite(beneficiary)}
                        type="button"
                      >
                        {beneficiary.is_favorite ? "FAV" : "Fav"}
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
                              setNotice(`${beneficiary.name} loaded into transfer details.`);
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
                          Use
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
                            setNotice(`${beneficiary.name} loaded into transfer details.`);
                            setError(null);
                            setTransferQuote(null);
                          }}
                          type="button"
                        >
                          Use
                        </button>
                      )}
                      <button
                        className="button--danger"
                        disabled={actionId === beneficiary.id}
                        onClick={() => deleteBeneficiary(beneficiary)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
                {!loading && beneficiaries.length === 0 && (
                  <div className="empty-state">No beneficiaries yet. Save one while sending a transfer.</div>
                )}
              </div>
            </section>

            <section className="tile backend-note">
              <span className="eyebrow">What the backend does</span>
              <p>IBAN transfer - external bank mock - debits your wallet ledger - optional beneficiary save</p>
            </section>
          </div>
        </div>
      ) : activeTab === "phone" ? (
        <form className="tile phone-transfer-card" onSubmit={handlePhoneTransfer}>
          <label>
            Phone number
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
                {phoneLookingUp ? "Finding..." : "Find"}
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
                <span>{phonePreview.destination_wallet_currency} wallet</span>
              </div>
              <span className="tag tag--accent">MATCH</span>
            </div>
          )}

          <label>
            Pay from
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
            Amount
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
            Description
            <input
              onChange={(event) => setPhoneForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Phone transfer"
              value={phoneForm.description}
            />
          </label>

          {phoneError && <p className="status-line status-line--error">{phoneError}</p>}
          {phoneNotice && <p className="status-line">{phoneNotice}</p>}

          <button
            disabled={phoneSending || !phonePreview || !phoneForm.source_wallet_id || !phoneForm.amount}
            type="submit"
          >
            {phoneSending ? "Sending..." : "Send by phone"}
          </button>
        </form>
      ) : activeTab === "qr" ? (
        <div className="qr-grid">
          <form className="tile qr-card" onSubmit={handleQrCreate}>
            <div>
              <span className="eyebrow">Payment request</span>
              <h2>Create QR request</h2>
            </div>

            <label>
              Destination wallet
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
              Amount
              <input
                min="0.01"
                onChange={(event) => setQrForm((current) => ({ ...current, amount: event.target.value }))}
                placeholder="Optional"
                step="0.01"
                type="number"
                value={qrForm.amount}
              />
            </label>

            <label>
              Expires in minutes
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

            <button disabled={qrCreating || !qrForm.destination_wallet_id} type="submit">
              {qrCreating ? "Creating..." : "Generate request"}
            </button>

            {qrRequest && (
              <div className="qr-result">
                <div className="qr-code" aria-label="Generated QR payment request preview" />
                <div className="qr-result__details">
                  <span className="eyebrow">Request id</span>
                  <code>{qrRequest.id}</code>
                  <span>
                    {qrRequest.amount ?? "Open amount"} {qrRequest.currency} - expires{" "}
                    {new Date(qrRequest.expires_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              </div>
            )}
          </form>

          <form className="tile qr-card" onSubmit={handleQrPay}>
            <div>
              <span className="eyebrow">Scan or paste</span>
              <h2>Pay QR request</h2>
            </div>

            <label>
              Request id
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
                  {qrLookingUp ? "Loading..." : "Load"}
                </button>
              </div>
            </label>

            {qrLookup && (
              <div className="request-summary">
                <span className="eyebrow">Active request</span>
                <strong>
                  {qrLookup.amount ?? "Open amount"} {qrLookup.currency}
                </strong>
                <span>Expires {new Date(qrLookup.expires_at).toLocaleString()}</span>
              </div>
            )}

            <label>
              Pay from
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
              Amount
              <input
                disabled={Boolean(qrLookup?.amount)}
                min="0.01"
                onChange={(event) => setQrPayForm((current) => ({ ...current, amount: event.target.value }))}
                placeholder={qrLookup?.amount ?? "Required for open requests"}
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
              {qrPaying ? "Paying..." : "Pay request"}
            </button>
          </form>

          <section className="tile backend-note qr-note">
            <span className="eyebrow">What the backend does</span>
            <p>payment_requests ACTIVE - QR carries request id only - payer confirms before transaction is created</p>
          </section>
        </div>
      ) : activeTab === "scheduled" ? (
        <div className="scheduled-grid">
          <form className="tile scheduled-form-card" onSubmit={handleScheduledSubmit}>
            <div>
              <span className="eyebrow">New scheduled payment</span>
              <h2>Create schedule</h2>
            </div>

            <label>
              Payee
              <input
                onChange={(event) =>
                  setScheduledForm((current) => ({ ...current, beneficiary_name: event.target.value }))
                }
                required
                value={scheduledForm.beneficiary_name}
              />
            </label>

            <label>
              IBAN
              <input
                onChange={(event) => setScheduledForm((current) => ({ ...current, iban: event.target.value }))}
                placeholder="RO49 AAAA 1B31 0075 9384 0000"
                required
                value={scheduledForm.iban}
              />
            </label>

            <label>
              Pay from
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
                Amount
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
                Currency
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
                Frequency
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
                      {frequency}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Next run
                <input
                  min={new Date().toISOString().slice(0, 10)}
                  onChange={(event) => setScheduledForm((current) => ({ ...current, next_run_on: event.target.value }))}
                  required
                  type="date"
                  value={scheduledForm.next_run_on}
                />
              </label>
              <label>
                Notify
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
              Description
              <input
                onChange={(event) => setScheduledForm((current) => ({ ...current, description: event.target.value }))}
                placeholder="Electricity bill"
                value={scheduledForm.description}
              />
            </label>

            {hasScheduledCurrencyMismatch && (
              <p className="status-line status-line--error">
                Scheduled payments currently require the source wallet currency to match the payment currency.
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
              {scheduledSubmitting ? "Creating..." : "Create scheduled payment"}
            </button>
          </form>

          <section className="tile scheduled-list-card">
            <div className="tile__header">
              <span className="eyebrow">Scheduled payments</span>
              {scheduledLoading && <span className="tag tag--neutral">Loading</span>}
            </div>

            <div className="scheduled-table">
              <div className="scheduled-row scheduled-row--head">
                <span>Payee</span>
                <span>Frequency</span>
                <span>Next run</span>
                <span>Notify</span>
                <span>Amount</span>
                <span>Status</span>
                <span />
              </div>
              {scheduledPayments.map((payment) => (
                <div className="scheduled-row" key={payment.id}>
                  <strong>{payment.beneficiary_name}</strong>
                  <span>{payment.frequency}</span>
                  <span>{new Date(`${payment.next_run_on}T00:00:00`).toLocaleDateString()}</span>
                  <span>{payment.notify_days_before} days before</span>
                  <strong>
                    {payment.amount} {payment.currency}
                  </strong>
                  <span className={`tag scheduled-status scheduled-status--${payment.status.toLowerCase()}`}>
                    {payment.status}
                  </span>
                  <div className="beneficiary-actions scheduled-actions">
                    {payment.status === "ACTIVE" && (
                      <button
                        className="button--ghost"
                        disabled={scheduledActionId === payment.id}
                        onClick={() => updateScheduledStatus(payment, "PAUSED")}
                        type="button"
                      >
                        Pause
                      </button>
                    )}
                    {payment.status === "PAUSED" && (
                      <button
                        className="button--ghost"
                        disabled={scheduledActionId === payment.id}
                        onClick={() => updateScheduledStatus(payment, "ACTIVE")}
                        type="button"
                      >
                        Resume
                      </button>
                    )}
                    {payment.status !== "CANCELLED" && (
                      <button
                        className="button--danger"
                        disabled={scheduledActionId === payment.id}
                        onClick={() => updateScheduledStatus(payment, "CANCELLED")}
                        type="button"
                      >
                        Cancel
                      </button>
                    )}
                    <button
                      className="button--danger"
                      disabled={scheduledActionId === payment.id}
                      onClick={() => deleteScheduledPayment(payment)}
                      type="button"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {!scheduledLoading && scheduledPayments.length === 0 && (
                <div className="empty-state">No scheduled payments yet.</div>
              )}
            </div>
          </section>

          <section className="tile backend-note scheduled-note">
            <span className="eyebrow">What the backend does</span>
            <p>scheduled_payments CRUD - owner scoped - validates source wallet - stores status for the future runner</p>
          </section>
        </div>
      ) : activeTab === "split" ? (
        <div className="scheduled-grid">
          <form className="tile scheduled-form-card" onSubmit={handleBillSplitSubmit}>
            <div>
              <span className="eyebrow">New bill split</span>
              <h2>Split a payment</h2>
            </div>

            <label>
              Title
              <input
                onChange={(event) => setBillSplitForm((current) => ({ ...current, title: event.target.value }))}
                placeholder="Dinner"
                required
                value={billSplitForm.title}
              />
            </label>

            <div className="amount-row">
              <label>
                Total amount
                <input
                  min="0.01"
                  onChange={(event) =>
                    setBillSplitForm((current) => ({
                      ...current,
                      total_amount: event.target.value,
                      participant_amount: current.participant_amount || event.target.value,
                    }))
                  }
                  required
                  step="0.01"
                  type="number"
                  value={billSplitForm.total_amount}
                />
              </label>
              <label>
                Currency
                <select
                  onChange={(event) => setBillSplitForm((current) => ({ ...current, currency: event.target.value }))}
                  value={billSplitForm.currency}
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
              Participant
              <select
                onChange={(event) => {
                  const beneficiary = beneficiaries.find((item) => item.id === event.target.value);
                  setBillSplitForm((current) => ({
                    ...current,
                    participant_user_id: beneficiary?.beneficiary_user_id ?? "",
                    participant_name: beneficiary?.name ?? "",
                    participant_phone: beneficiary?.phone ?? "",
                  }));
                }}
                value={beneficiaries.find((item) => item.beneficiary_user_id === billSplitForm.participant_user_id)?.id ?? ""}
              >
                <option value="">Manual participant</option>
                {internalBeneficiaries.map((beneficiary) => (
                  <option key={beneficiary.id} value={beneficiary.id}>
                    {beneficiary.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Participant user id
              <input
                onChange={(event) =>
                  setBillSplitForm((current) => ({ ...current, participant_user_id: event.target.value }))
                }
                placeholder="Use a saved internal beneficiary or paste a user id"
                value={billSplitForm.participant_user_id}
              />
            </label>

            <label>
              Participant name
              <input
                onChange={(event) =>
                  setBillSplitForm((current) => ({ ...current, participant_name: event.target.value }))
                }
                required
                value={billSplitForm.participant_name}
              />
            </label>

            <div className="amount-row">
              <label>
                Phone
                <input
                  onChange={(event) =>
                    setBillSplitForm((current) => ({ ...current, participant_phone: event.target.value }))
                  }
                  value={billSplitForm.participant_phone}
                />
              </label>
              <label>
                Share amount
                <input
                  min="0.01"
                  onChange={(event) =>
                    setBillSplitForm((current) => ({ ...current, participant_amount: event.target.value }))
                  }
                  required
                  step="0.01"
                  type="number"
                  value={billSplitForm.participant_amount}
                />
              </label>
            </div>

            <label>
              Source transaction
              <select
                onChange={(event) =>
                  setBillSplitForm((current) => ({ ...current, source_transaction_id: event.target.value }))
                }
                value={billSplitForm.source_transaction_id}
              >
                <option value="">No linked transaction</option>
                {transactions.map((transaction) => (
                  <option key={transaction.id} value={transaction.id}>
                    {transaction.description || transaction.type} - {transaction.amount} {transaction.currency}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Description
              <input
                onChange={(event) =>
                  setBillSplitForm((current) => ({ ...current, description: event.target.value }))
                }
                placeholder="Pizza and drinks"
                value={billSplitForm.description}
              />
            </label>

            {splitError && <p className="status-line status-line--error">{splitError}</p>}
            {splitNotice && <p className="status-line">{splitNotice}</p>}

            <button disabled={splitSubmitting} type="submit">
              {splitSubmitting ? "Creating..." : "Create bill split"}
            </button>
          </form>

          <section className="tile scheduled-list-card">
            <div className="tile__header">
              <span className="eyebrow">Bill splits</span>
              {splitLoading && <span className="tag tag--neutral">Loading</span>}
            </div>
            <div className="bill-split-table">
              {billSplits.map((split) => (
                <div className="bill-split-row" key={split.id}>
                  <div className="bill-split-row__main">
                    <strong>{split.title}</strong>
                    <span>{split.total_amount} {split.currency}</span>
                    <span className={`tag scheduled-status scheduled-status--${split.status.toLowerCase()}`}>
                      {split.status}
                    </span>
                    <span>{split.participants.length} participant(s)</span>
                  </div>
                  <div className="bill-split-row__participants">
                    {split.participants.map((participant) => (
                      <div className="bill-split-participant" key={participant.id}>
                        <span className="eyebrow">{participant.status}</span>
                        <strong>{participant.name}</strong>
                        <span>{participant.amount} {split.currency}</span>
                        {participant.status === "PENDING" && participant.participant_user_id === user?.id && (
                          <button
                            className="button--wide"
                            disabled={splitActionId === participant.id}
                            onClick={() => payBillSplit(split, participant.id)}
                            type="button"
                          >
                            {splitActionId === participant.id ? "Paying..." : "Pay share"}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="beneficiary-actions bill-split-row__actions">
                    {split.status === "OPEN" && split.owner_user_id === user?.id && (
                      <button
                        className="button--danger button--wide"
                        disabled={splitActionId === split.id}
                        onClick={() => cancelBillSplit(split)}
                        type="button"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {!splitLoading && billSplits.length === 0 && (
                <div className="empty-state">No bill splits yet.</div>
              )}
            </div>
          </section>

          <section className="tile backend-note scheduled-note">
            <span className="eyebrow">What the backend does</span>
            <p>bill_splits + participants - owner scoped - participants pay through the internal transfer engine</p>
          </section>
        </div>
      ) : activeTab === "folders" ? (
        <div className="scheduled-grid">
          <form className="tile scheduled-form-card" onSubmit={handleFolderSubmit}>
            <div>
              <span className="eyebrow">New folder</span>
              <h2>Organize transactions</h2>
            </div>

            <label>
              Name
              <input
                onChange={(event) => setFolderForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="Rent"
                required
                value={folderForm.name}
              />
            </label>

            <label>
              Color
              <select
                onChange={(event) => setFolderForm((current) => ({ ...current, color: event.target.value }))}
                value={folderForm.color}
              >
                <option value="violet">Violet</option>
                <option value="blue">Blue</option>
                <option value="green">Green</option>
                <option value="orange">Orange</option>
              </select>
            </label>

            <label>
              Description
              <input
                onChange={(event) => setFolderForm((current) => ({ ...current, description: event.target.value }))}
                placeholder="Apartment payments"
                value={folderForm.description}
              />
            </label>

            {folderError && <p className="status-line status-line--error">{folderError}</p>}
            {folderNotice && <p className="status-line">{folderNotice}</p>}

            <button disabled={folderSubmitting} type="submit">
              {folderSubmitting ? "Creating..." : "Create folder"}
            </button>
          </form>

          <section className="tile scheduled-list-card">
            <div className="tile__header">
              <span className="eyebrow">Transaction folders</span>
              {folderLoading && <span className="tag tag--neutral">Loading</span>}
            </div>

            <div className="scheduled-table">
              {transactionFolders.map((folder) => (
                <div className="scheduled-row" key={folder.id}>
                  <strong>{folder.name}</strong>
                  <span>{folder.description || "No description"}</span>
                  <span className="tag tag--outline">{folder.items.length} tx</span>
                  <div className="beneficiary-actions scheduled-actions">
                    <button
                      className="button--ghost"
                      onClick={() => setSelectedFolderId(folder.id)}
                      type="button"
                    >
                      Select
                    </button>
                    <button
                      className="button--danger"
                      disabled={folderActionId === folder.id}
                      onClick={() => deleteTransactionFolder(folder)}
                      type="button"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {!folderLoading && transactionFolders.length === 0 && (
                <div className="empty-state">No transaction folders yet.</div>
              )}
            </div>

            {selectedFolder && (
              <form className="request-summary" onSubmit={addTransactionToFolder}>
                <span className="eyebrow">Selected folder</span>
                <strong>{selectedFolder.name}</strong>
                <select
                  onChange={(event) => setFolderTransactionId(event.target.value)}
                  value={folderTransactionId}
                >
                  <option value="">Choose transaction</option>
                  {folderCandidateTransactions.map((transaction) => (
                    <option key={transaction.id} value={transaction.id}>
                      {transaction.description || transaction.type} - {transaction.amount} {transaction.currency}
                    </option>
                  ))}
                </select>
                <button disabled={!folderTransactionId || Boolean(folderActionId)} type="submit">
                  Add transaction
                </button>
                {selectedFolder.items.map((item) => {
                  const transaction = transactions.find((candidate) => candidate.id === item.transaction_id);
                  return (
                    <div className="match-card" key={item.id}>
                      <div className="beneficiary-meta">
                        <strong>{transaction?.description || transaction?.type || item.transaction_id}</strong>
                        <span>{transaction ? `${transaction.amount} ${transaction.currency}` : "Transaction"}</span>
                      </div>
                      <button
                        className="button--danger"
                        disabled={folderActionId === item.transaction_id}
                        onClick={() => removeTransactionFromFolder(selectedFolder.id, item.transaction_id)}
                        type="button"
                      >
                        Remove
                      </button>
                    </div>
                  );
                })}
              </form>
            )}
          </section>

          <section className="tile backend-note scheduled-note">
            <span className="eyebrow">What the backend does</span>
            <p>transaction_folders - owner scoped - stores transaction references without changing ledger rows</p>
          </section>
        </div>
      ) : (
        <section className="tile tab-panel-placeholder">
          <span className="eyebrow">{TABS.find((tab) => tab.id === activeTab)?.label}</span>
          <p>This payment flow is next for Dev 2. Beneficiaries are available now.</p>
        </section>
      )}
    </section>
  );
}

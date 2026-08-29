import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ApiError, apiRequest } from "../api/apiClient";
import { BILL_SPLIT_CHANGED_EVENT } from "../events";
import { CategoryIcon } from "../features/transactions";
import { useAuth } from "../hooks/useAuth";
import type {
  Beneficiary,
  BillSplit,
  Transaction,
  TransactionCategory,
  TransactionFolder,
  Wallet,
} from "../types";

const FOLDER_NAME_MAX_LENGTH = 40;
const FOLDER_DESCRIPTION_MAX_LENGTH = 120;
const TRANSACTIONS_PER_PAGE = 15;

interface SplitParticipantDraft {
  key: string;
  name: string;
  participant_user_id: string;
  phone: string;
  percent: string;
}

// Money coming in only (not a self-transfer between the user's own
// wallets, which is both incoming and outgoing) -- salary, cashback,
// received transfers, etc. There's no bill to split for money you received.
function isIncomingOnly(transaction: Transaction, userWalletIds: Set<string>): boolean {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  return isIncoming && !isOutgoing;
}

// Mirrors backend/app/payments/service.py's SPLITTABLE_TRANSACTION_TYPES /
// FOLDER_ELIGIBLE_TRANSACTION_TYPES: transfers, FX conversions, loan
// installments, and bill-split settlements are never a "payment" either
// feature is meant for.
const SPLITTABLE_TRANSACTION_TYPES = new Set(["CARD_PAYMENT", "SCHEDULED_PAYMENT"]);
const FOLDER_ELIGIBLE_TRANSACTION_TYPES = new Set([...SPLITTABLE_TRANSACTION_TYPES, "CASHBACK"]);

function isSplittable(transaction: Transaction): boolean {
  return SPLITTABLE_TRANSACTION_TYPES.has(transaction.type);
}

function isFolderEligible(transaction: Transaction): boolean {
  return FOLDER_ELIGIBLE_TRANSACTION_TYPES.has(transaction.type);
}

function formatAmount(transaction: Transaction, userWalletIds: Set<string>): string {
  const sign = isIncomingOnly(transaction, userWalletIds) ? "+" : "-";
  return `${sign}${transaction.amount} ${transaction.currency}`;
}

function formatTransactionType(
  transaction: Transaction,
  userWalletIds: Set<string>,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const description = transaction.description?.toLowerCase() ?? "";
  if (description.includes("loan") && description.includes("disbursement") && isIncomingOnly(transaction, userWalletIds)) {
    return t("transactions.bankToUser");
  }
  if (transaction.type === "LOAN_PAYMENT") {
    return t("transactions.userToBank");
  }
  return t(`common.txType.${transaction.type}`, { defaultValue: transaction.type.replaceAll("_", " ") });
}

function toNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function moneyFromPercent(total: string, percent: string): string {
  return ((toNumber(total) * toNumber(percent)) / 100).toFixed(2);
}

function percentInput(value: string): string {
  if (value.trim() === "") return "";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "";
  const clamped = Math.min(100, Math.max(0, parsed));
  return String(clamped);
}

// Splitting a transaction that is itself the result of a previous split
// (description "Bill split payment - Split: <original>") would otherwise
// keep nesting "Bill split payment - Split: " on every re-split. Strip any
// prior wrapping first so the new title always reads "Split: <original>".
function baseSplitDescription(description: string): string {
  let base = description;
  let stripped = true;
  while (stripped) {
    stripped = false;
    if (base.startsWith("Bill split payment - ")) {
      base = base.slice("Bill split payment - ".length);
      stripped = true;
    }
    if (base.startsWith("Split: ")) {
      base = base.slice("Split: ".length);
      stripped = true;
    }
  }
  return base;
}

export function TransactionsPage() {
  const { t } = useTranslation();
  const { accessToken, user } = useAuth();
  const navigate = useNavigate();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [billSplits, setBillSplits] = useState<BillSplit[]>([]);
  const [transactionFolders, setTransactionFolders] = useState<TransactionFolder[]>([]);
  const [splitTransaction, setSplitTransaction] = useState<Transaction | null>(null);
  const [splitParticipants, setSplitParticipants] = useState<SplitParticipantDraft[]>([]);
  const [folderTransaction, setFolderTransaction] = useState<Transaction | null>(null);
  const [folderName, setFolderName] = useState("");
  const [folderDescription, setFolderDescription] = useState("");
  const [folderError, setFolderError] = useState<string | null>(null);
  const [folderNotice, setFolderNotice] = useState<string | null>(null);
  const [folderActionId, setFolderActionId] = useState<string | null>(null);
  const [folderCreating, setFolderCreating] = useState(false);
  const [splitNotice, setSplitNotice] = useState<string | null>(null);
  const [splitError, setSplitError] = useState<string | null>(null);
  const [splitSubmitting, setSplitSubmitting] = useState(false);
  const [splitActionId, setSplitActionId] = useState<string | null>(null);
  const [categories, setCategories] = useState<TransactionCategory[]>([]);
  const [categoryTransaction, setCategoryTransaction] = useState<Transaction | null>(null);
  const [categorySaving, setCategorySaving] = useState(false);
  const [categoryError, setCategoryError] = useState<string | null>(null);
  const [transactionsLoading, setTransactionsLoading] = useState(false);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);
  const [transactionsPage, setTransactionsPage] = useState(1);

  useEffect(() => {
    if (!accessToken) return;
    void refreshTransactionsData();
    apiRequest<Beneficiary[]>("/payments/beneficiaries", { token: accessToken })
      .then(setBeneficiaries)
      .catch(() => setBeneficiaries([]));
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return;
    function handleBillSplitChanged() {
      void refreshTransactionsData();
    }
    window.addEventListener(BILL_SPLIT_CHANGED_EVENT, handleBillSplitChanged);
    return () => window.removeEventListener(BILL_SPLIT_CHANGED_EVENT, handleBillSplitChanged);
  }, [accessToken]);

  useEffect(() => {
    setTransactionsPage((currentPage) => {
      const maxPage = Math.max(1, Math.ceil(transactions.length / TRANSACTIONS_PER_PAGE));
      return Math.min(currentPage, maxPage);
    });
  }, [transactions.length]);

  const userWalletIds = new Set(wallets.map((wallet) => wallet.id));
  const internalBeneficiaries = beneficiaries.filter((beneficiary) => beneficiary.beneficiary_user_id);
  const pendingSplitRequests = billSplits.flatMap((split) =>
    split.participants
      .filter((participant) => participant.status === "PENDING" && participant.participant_user_id === user?.id)
      .map((participant) => ({ split, participant })),
  );
  const ownedOpenSplits = billSplits.filter((split) => split.owner_user_id === user?.id && split.status === "OPEN");
  const transactionPageCount = Math.max(1, Math.ceil(transactions.length / TRANSACTIONS_PER_PAGE));
  const currentTransactionsPage = Math.min(transactionsPage, transactionPageCount);
  const transactionsPageStart = (currentTransactionsPage - 1) * TRANSACTIONS_PER_PAGE;
  const visibleTransactions = transactions.slice(transactionsPageStart, transactionsPageStart + TRANSACTIONS_PER_PAGE);
  const firstVisibleTransaction = transactions.length === 0 ? 0 : transactionsPageStart + 1;
  const lastVisibleTransaction = Math.min(transactionsPageStart + TRANSACTIONS_PER_PAGE, transactions.length);
  const transactionPageButtonCount = Math.min(5, transactionPageCount);
  const firstTransactionPageButton = Math.min(
    Math.max(1, currentTransactionsPage - 2),
    Math.max(1, transactionPageCount - transactionPageButtonCount + 1),
  );
  const transactionPageNumbers = Array.from(
    { length: transactionPageButtonCount },
    (_, index) => firstTransactionPageButton + index,
  );

  async function loadBillSplits() {
    if (!accessToken) return;
    try {
      const list = await apiRequest<BillSplit[]>("/payments/bill-splits", { token: accessToken });
      setBillSplits(list);
    } catch {
      setBillSplits([]);
    }
  }

  async function refreshTransactionsData() {
    if (!accessToken) return;
    setTransactionsLoading(true);
    setTransactionsError(null);
    try {
      const [nextTransactions, nextWallets, nextBillSplits, nextCategories] = await Promise.all([
        apiRequest<Transaction[]>("/transactions", { token: accessToken }),
        apiRequest<Wallet[]>("/wallets", { token: accessToken }).catch(() => []),
        apiRequest<BillSplit[]>("/payments/bill-splits", { token: accessToken }).catch(() => []),
        apiRequest<TransactionCategory[]>("/transactions/categories", { token: accessToken }).catch(() => []),
      ]);
      setTransactions(nextTransactions);
      setWallets(nextWallets);
      setBillSplits(nextBillSplits);
      setCategories(nextCategories);
      await loadTransactionFolders();
    } catch (err) {
      setTransactions([]);
      setTransactionsError(err instanceof ApiError ? err.message : t("transactions.couldNotLoad"));
    } finally {
      setTransactionsLoading(false);
    }
  }

  function openSplit(transaction: Transaction) {
    setSplitTransaction(transaction);
    setSplitParticipants([]);
    setSplitNotice(null);
    setSplitError(null);
  }

  async function loadTransactionFolders() {
    if (!accessToken) return;
    try {
      const list = await apiRequest<TransactionFolder[]>("/payments/transaction-folders", { token: accessToken });
      setTransactionFolders(list);
    } catch {
      setTransactionFolders([]);
    }
  }

  function openCategoryModal(transaction: Transaction) {
    setCategoryTransaction(transaction);
    setCategoryError(null);
  }

  async function applyCategory(categoryId: string | null) {
    if (!accessToken || !categoryTransaction) return;
    setCategorySaving(true);
    setCategoryError(null);
    try {
      const updated = await apiRequest<Transaction>(
        `/transactions/${categoryTransaction.id}/category`,
        { method: "PATCH", token: accessToken, body: { category_id: categoryId } },
      );
      // Patch the row in place rather than refetching the list: the amount,
      // status and ledger are untouched by a re-categorisation, so the only
      // thing that can have changed is this row's own category.
      setTransactions((current) => current.map((tx) => (tx.id === updated.id ? updated : tx)));
      setCategoryTransaction(null);
    } catch (err) {
      setCategoryError(err instanceof ApiError ? err.message : t("transactions.couldNotChangeCategory"));
    } finally {
      setCategorySaving(false);
    }
  }

  function openFolderModal(transaction: Transaction) {
    setFolderTransaction(transaction);
    setFolderError(null);
    setFolderNotice(null);
    setFolderName("");
    setFolderDescription("");
    void loadTransactionFolders();
  }

  async function createFolder() {
    if (!accessToken || !folderName.trim()) return;
    if (folderName.length > FOLDER_NAME_MAX_LENGTH) {
      setFolderError(t("transactions.folderTitleTooLong", { max: FOLDER_NAME_MAX_LENGTH }));
      return;
    }
    if (folderDescription.length > FOLDER_DESCRIPTION_MAX_LENGTH) {
      setFolderError(t("transactions.folderDescriptionTooLong", { max: FOLDER_DESCRIPTION_MAX_LENGTH }));
      return;
    }
    setFolderCreating(true);
    setFolderError(null);
    setFolderNotice(null);
    try {
      const folder = await apiRequest<TransactionFolder>("/payments/transaction-folders", {
        method: "POST",
        token: accessToken,
        body: {
          name: folderName.trim(),
          color: "violet",
          description: folderDescription.trim() || null,
        },
      });
      setTransactionFolders((current) => [folder, ...current]);
      setFolderName("");
      setFolderDescription("");
      setFolderNotice(t("transactions.folderCreated"));
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : t("transactions.couldNotCreateFolder"));
    } finally {
      setFolderCreating(false);
    }
  }

  async function addTransactionToFolder(folder: TransactionFolder) {
    if (!accessToken || !folderTransaction) return;
    setFolderActionId(folder.id);
    setFolderError(null);
    setFolderNotice(null);
    try {
      await apiRequest<TransactionFolder>(`/payments/transaction-folders/${folder.id}/transactions`, {
        method: "POST",
        token: accessToken,
        body: { transaction_id: folderTransaction.id },
      });
      setFolderNotice(t("transactions.transactionAddedToFolder"));
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : t("transactions.couldNotAddToFolder"));
    } finally {
      setFolderActionId(null);
    }
  }

  function toggleSplitBeneficiary(beneficiary: Beneficiary) {
    if (!beneficiary.beneficiary_user_id) return;
    setSplitParticipants((current) => {
      const exists = current.some((participant) => participant.key === beneficiary.id);
      const next = exists
        ? current.filter((participant) => participant.key !== beneficiary.id)
        : [
            ...current,
            {
              key: beneficiary.id,
              name: beneficiary.name,
              participant_user_id: beneficiary.beneficiary_user_id ?? "",
              phone: beneficiary.phone ?? "",
              percent: "",
            },
          ];
      const equalPercent = next.length > 0 ? (100 / (next.length + 1)).toFixed(2) : "";
      return next.map((participant) => ({ ...participant, percent: equalPercent }));
    });
  }

  function addManualParticipant() {
    setSplitParticipants((current) => [
      ...current,
      {
        key: crypto.randomUUID(),
        name: "",
        participant_user_id: "",
        phone: "",
        percent: current.length === 0 ? "50.00" : "",
      },
    ]);
  }

  function updateSplitParticipant(key: string, changes: Partial<SplitParticipantDraft>) {
    setSplitParticipants((current) =>
      current.map((participant) => (participant.key === key ? { ...participant, ...changes } : participant)),
    );
  }

  function removeSplitParticipant(key: string) {
    setSplitParticipants((current) => current.filter((participant) => participant.key !== key));
  }

  function splitEqually() {
    setSplitParticipants((current) => {
      if (current.length === 0) return current;
      const percent = (100 / (current.length + 1)).toFixed(2);
      return current.map((participant) => ({ ...participant, percent }));
    });
  }

  async function submitSplitBill() {
    if (!accessToken || !splitTransaction) return;
    const requestedPercent = splitParticipants.reduce((sum, participant) => sum + toNumber(participant.percent), 0);
    if (splitParticipants.length === 0) {
      setSplitError(t("transactions.chooseAtLeastOnePerson"));
      return;
    }
    if (requestedPercent <= 0 || requestedPercent > 100) {
      setSplitError(t("transactions.sharesRange"));
      return;
    }
    if (
      splitParticipants.some(
        (participant) => !participant.name.trim() || (!participant.participant_user_id.trim() && !participant.phone.trim()),
      )
    ) {
      setSplitError(t("transactions.needNameAndPhone"));
      return;
    }

    setSplitSubmitting(true);
    setSplitError(null);
    setSplitNotice(null);
    try {
      await apiRequest<BillSplit>("/payments/bill-splits", {
        method: "POST",
        token: accessToken,
        body: {
          title: splitTransaction.description
            ? t("transactions.splitTitle", { description: baseSplitDescription(splitTransaction.description) })
            : t("transactions.splitBillFallback"),
          total_amount: splitTransaction.amount,
          currency: splitTransaction.currency,
          source_transaction_id: splitTransaction.id,
          description: t("transactions.createdFromSplit"),
          participants: splitParticipants.map((participant) => ({
            participant_user_id: participant.participant_user_id.trim() || null,
            name: participant.name.trim(),
            phone: participant.phone.trim() || null,
            percent: participant.percent,
          })),
        },
      });
      setSplitNotice(t("transactions.splitRequestsSent"));
      setSplitTransaction(null);
      setSplitParticipants([]);
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : t("transactions.couldNotCreateSplit"));
    } finally {
      setSplitSubmitting(false);
    }
  }

  async function paySplitRequest(split: BillSplit, participantId: string) {
    if (!accessToken) return;
    const sourceWallet = wallets.find((wallet) => wallet.currency === split.currency);
    if (!sourceWallet) {
      setSplitError(t("transactions.noWalletForPayment", { currency: split.currency }));
      return;
    }
    setSplitActionId(participantId);
    setSplitError(null);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/participants/${participantId}/pay`, {
        method: "POST",
        token: accessToken,
        body: { source_wallet_id: sourceWallet.id },
      });
      setSplitNotice(t("transactions.splitBillPaid"));
      await refreshTransactionsData();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : t("transactions.couldNotPaySplit"));
    } finally {
      setSplitActionId(null);
    }
  }

  async function refuseSplitRequest(split: BillSplit, participantId: string) {
    if (!accessToken) return;
    setSplitActionId(participantId);
    setSplitError(null);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/participants/${participantId}/decline`, {
        method: "POST",
        token: accessToken,
      });
      setSplitNotice(t("transactions.splitBillRefused"));
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : t("transactions.couldNotRefuseSplit"));
    } finally {
      setSplitActionId(null);
    }
  }

  async function cancelOwnedSplit(split: BillSplit) {
    if (!accessToken) return;
    setSplitActionId(split.id);
    setSplitError(null);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/cancel`, {
        method: "PATCH",
        token: accessToken,
      });
      setSplitNotice(t("transactions.splitBillCancelled"));
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : t("transactions.couldNotCancelSplit"));
    } finally {
      setSplitActionId(null);
    }
  }

  return (
    <section>
      <div className="transactions-header">
        <h2>{t("transactions.title")}</h2>
        <button className="button--ghost button--wide" onClick={() => void refreshTransactionsData()} type="button">
          {t("transactions.refresh")}
        </button>
      </div>
      {transactionsError && <p className="status-line status-line--error">{transactionsError}</p>}
      {splitNotice && <p className="status-line">{splitNotice}</p>}
      {pendingSplitRequests.length > 0 && (
        <div className="transaction-split-requests">
          {pendingSplitRequests.map(({ split, participant }) => (
            <div className="transaction-split-request" key={participant.id}>
              <div>
                <span className="eyebrow">{t("transactions.splitBillRequest")}</span>
                <strong>{split.title}</strong>
                <span>
                  {t("transactions.asksFor", { name: participant.name, amount: participant.amount, currency: split.currency })}
                </span>
              </div>
              <div className="transaction-split-request__actions">
                <button
                  className="button--wide"
                  disabled={splitActionId === participant.id}
                  onClick={() => paySplitRequest(split, participant.id)}
                  type="button"
                >
                  {t("transactions.pay")}
                </button>
                <button
                  className="button--wide button--ghost"
                  disabled={splitActionId === participant.id}
                  onClick={() => refuseSplitRequest(split, participant.id)}
                  type="button"
                >
                  {t("transactions.refuse")}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {ownedOpenSplits.length > 0 && (
        <div className="transaction-split-requests">
          {ownedOpenSplits.map((split) => {
            const paidCount = split.participants.filter((participant) => participant.status === "PAID").length;
            return (
              <div className="transaction-split-request" key={split.id}>
                <div>
                  <span className="eyebrow">{t("transactions.yourSplit")}</span>
                  <strong>{split.title}</strong>
                  <span>
                    {t("transactions.paidOf", { paid: paidCount, total: split.participants.length })} &middot; {split.total_amount} {split.currency}
                  </span>
                </div>
                <div className="transaction-split-request__actions">
                  <button
                    className="button--wide button--ghost"
                    disabled={splitActionId === split.id}
                    onClick={() => cancelOwnedSplit(split)}
                    type="button"
                  >
                    {splitActionId === split.id ? t("transactions.cancelling") : t("transactions.cancel")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {splitTransaction ? (
        <div className="tile split-builder">
          <div className="tile__header">
            <span className="eyebrow">{t("transactions.splitBill")}</span>
            <button className="button--ghost" type="button" onClick={() => setSplitTransaction(null)}>
              {t("transactions.close")}
            </button>
          </div>
          <div className="split-builder__summary">
            <strong>{splitTransaction.description || splitTransaction.type}</strong>
            <span>
              {splitTransaction.amount} {splitTransaction.currency} {t("transactions.on")}{" "}
              {new Date(splitTransaction.created_at).toLocaleDateString()}
            </span>
          </div>
          {internalBeneficiaries.length > 0 ? (
            <div className="split-beneficiary-picker">
              {internalBeneficiaries.map((beneficiary) => {
                const checked = splitParticipants.some((participant) => participant.key === beneficiary.id);
                return (
                  <label className="checkbox-row" key={beneficiary.id}>
                    <input
                      checked={checked}
                      onChange={() => toggleSplitBeneficiary(beneficiary)}
                      type="checkbox"
                    />
                    {beneficiary.name}
                  </label>
                );
              })}
            </div>
          ) : (
            <p className="status-line">{t("transactions.noBeneficiariesYet")}</p>
          )}
          <div className="form-actions">
            <button className="button--ghost" onClick={splitEqually} type="button">
              {t("transactions.splitEqually")}
            </button>
            <button className="button--ghost" onClick={addManualParticipant} type="button">
              {t("transactions.addPerson")}
            </button>
          </div>
          <div className="split-participant-list">
            {splitParticipants.map((participant) => (
              <div className="split-participant-row" key={participant.key}>
                <label>
                  {t("transactions.recipientName")}
                  <input
                    onChange={(event) => updateSplitParticipant(participant.key, { name: event.target.value })}
                    placeholder="Maria Dinu"
                    value={participant.name}
                  />
                </label>
                <label>
                  {t("transactions.phoneNumber")}
                  <input
                    onChange={(event) => updateSplitParticipant(participant.key, { phone: event.target.value })}
                    placeholder="+40700000101"
                    value={participant.phone}
                  />
                </label>
                <label>
                  {t("transactions.percent")}
                  <input
                    min="0"
                    max="100"
                    onChange={(event) =>
                      updateSplitParticipant(participant.key, { percent: percentInput(event.target.value) })
                    }
                    step="0.01"
                    type="number"
                    value={participant.percent}
                  />
                </label>
                <div className="split-participant-row__amount">
                  <span>{moneyFromPercent(splitTransaction.amount, participant.percent)}</span>
                  <small>{splitTransaction.currency}</small>
                </div>
                <button className="button--danger" onClick={() => removeSplitParticipant(participant.key)} type="button">
                  {t("transactions.remove")}
                </button>
              </div>
            ))}
          </div>
          {splitParticipants.length > 0 && (
            <p className="status-line">
              {t("transactions.requestedTotal", {
                amount: moneyFromPercent(splitTransaction.amount, String(splitParticipants.reduce((sum, participant) => sum + toNumber(participant.percent), 0))),
                currency: splitTransaction.currency,
              })}
            </p>
          )}
          {splitError && <p className="status-line status-line--error">{splitError}</p>}
          <button disabled={splitSubmitting || splitParticipants.length === 0} onClick={submitSplitBill} type="button">
            {splitSubmitting ? t("transactions.sending") : t("transactions.sendMoneyRequests")}
          </button>
        </div>
      ) : null}
      {categoryTransaction ? (
        <div className="folder-modal-backdrop" role="presentation">
          <section
            className="tile folder-modal"
            role="dialog"
            aria-modal="true"
            aria-label={t("transactions.changeCategory")}
          >
            <div className="tile__header">
              <div>
                <span className="eyebrow">{t("transactions.changeCategory")}</span>
                <h2>{categoryTransaction.description || categoryTransaction.type}</h2>
              </div>
              <button className="button--ghost" onClick={() => setCategoryTransaction(null)} type="button">
                {t("transactions.close")}
              </button>
            </div>
            {categoryError && <p className="status-line status-line--error">{categoryError}</p>}
            <div className="category-choices">
              {categories.map((category) => {
                const active = categoryTransaction.category === category.name;
                return (
                  <button
                    className={active ? "category-choice category-choice--active" : "category-choice"}
                    disabled={categorySaving}
                    key={category.id}
                    onClick={() => applyCategory(category.id)}
                    type="button"
                  >
                    <CategoryIcon category={category.name} size={18} />
                    <span>{category.name}</span>
                  </button>
                );
              })}
            </div>
            {/* Only offered once the user has actually overridden something
                — there is nothing to reset back to while the category still
                comes from the merchant. */}
            {categoryTransaction.category_id && (
              <div className="category-modal__footer">
                <button
                  className="button--ghost button--wide"
                  disabled={categorySaving}
                  onClick={() => applyCategory(null)}
                  type="button"
                >
                  {t("transactions.resetCategoryToMerchant")}
                </button>
              </div>
            )}
          </section>
        </div>
      ) : null}
      {folderTransaction ? (
        <div className="folder-modal-backdrop" role="presentation">
          <section className="tile folder-modal" role="dialog" aria-modal="true" aria-label={t("transactions.addTransactionToFolderLabel")}>
            <div className="tile__header">
              <div>
                <span className="eyebrow">{t("transactions.addToFolder")}</span>
                <h2>{folderTransaction.description || folderTransaction.type}</h2>
              </div>
              <button className="button--ghost" onClick={() => setFolderTransaction(null)} type="button">
                {t("transactions.close")}
              </button>
            </div>

            <div className="folder-modal__create">
              <label>
                {t("transactions.folderTitle")}
                <input
                  maxLength={FOLDER_NAME_MAX_LENGTH}
                  onChange={(event) => setFolderName(event.target.value)}
                  placeholder="Travel"
                  value={folderName}
                />
                <span className="field-hint">
                  {folderName.length}/{FOLDER_NAME_MAX_LENGTH}
                </span>
              </label>
              <label>
                {t("transactions.description")}
                <input
                  maxLength={FOLDER_DESCRIPTION_MAX_LENGTH}
                  onChange={(event) => setFolderDescription(event.target.value)}
                  placeholder={t("transactions.optional")}
                  value={folderDescription}
                />
                <span className="field-hint">
                  {folderDescription.length}/{FOLDER_DESCRIPTION_MAX_LENGTH}
                </span>
              </label>
              <button className="button--wide" disabled={folderCreating || !folderName.trim()} onClick={createFolder} type="button">
                {folderCreating ? t("transactions.creating") : t("transactions.createNewFolder")}
              </button>
            </div>

            {folderError && <p className="status-line status-line--error">{folderError}</p>}
            {folderNotice && <p className="status-line">{folderNotice}</p>}

            <div className="folder-modal__list">
              {transactionFolders.map((folder) => {
                const alreadyAdded = folder.items.some((item) => item.transaction_id === folderTransaction.id);
                if (alreadyAdded) {
                  return (
                    <div className="folder-choice folder-choice--active" key={folder.id}>
                      <span>
                        <strong>{folder.name}</strong>
                        <small>{folder.description || t("transactions.transactionCount", { count: folder.items.length })}</small>
                      </span>
                      <div className="folder-choice__actions">
                        <span>{t("transactions.added")}</span>
                        <button
                          className="button--ghost button--wide"
                          onClick={() => navigate(`/payments?tab=folders&folder=${folder.id}`)}
                          type="button"
                        >
                          {t("transactions.goToFolder")}
                        </button>
                      </div>
                    </div>
                  );
                }
                return (
                  <button
                    className="folder-choice"
                    disabled={folderActionId === folder.id}
                    key={folder.id}
                    onClick={() => addTransactionToFolder(folder)}
                    type="button"
                  >
                    <span>
                      <strong>{folder.name}</strong>
                      <small>{folder.description || t("transactions.transactionCount", { count: folder.items.length })}</small>
                    </span>
                    <span>{t("transactions.add")}</span>
                  </button>
                );
              })}
              {transactionFolders.length === 0 && (
                <div className="empty-state">{t("transactions.noFoldersYet")}</div>
              )}
            </div>
          </section>
        </div>
      ) : null}
      <section className="tile transactions-table-card">
        {transactionsLoading ? (
          <div className="empty-state">{t("transactions.loadingTransactions")}</div>
        ) : transactions.length === 0 ? (
          <div className="empty-state">{t("transactions.noTransactionsFound", { name: user?.first_name ?? t("transactions.thisUser") })}</div>
        ) : (
          <table className="transactions-table">
            <thead>
              <tr>
                <th>{t("transactions.date")}</th>
                <th>{t("transactions.type")}</th>
                <th>{t("transactions.description")}</th>
                <th>{t("transactions.amount")}</th>
                <th>{t("transactions.status")}</th>
                <th>{t("transactions.action")}</th>
              </tr>
            </thead>
            <tbody>
              {visibleTransactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{new Date(tx.created_at).toLocaleString()}</td>
                  <td>{formatTransactionType(tx, userWalletIds, t)}</td>
                  <td>
                    <span className="transaction-description">
                      <span className="transaction-description__text">{tx.description}</span>
                      {tx.category && <CategoryIcon category={tx.category} />}
                    </span>
                  </td>
                  <td className={isIncomingOnly(tx, userWalletIds) ? "transaction-amount--in" : "transaction-amount--out"}>
                    {formatAmount(tx, userWalletIds)}
                  </td>
                  <td>{t(`common.status.${tx.status}`, { defaultValue: tx.status })}</td>
                  <td>
                    <div className="transaction-actions">
                      {tx.status === "COMPLETED" && isSplittable(tx) ? (
                        <button className="button--ghost button--wide" onClick={() => openSplit(tx)} type="button">
                          {t("transactions.splitBill")}
                        </button>
                      ) : (
                        <span className="button--ghost button--wide transaction-actions__placeholder" aria-hidden="true" />
                      )}
                      {tx.status === "COMPLETED" && isFolderEligible(tx) ? (
                        <button className="button--ghost button--wide" onClick={() => openFolderModal(tx)} type="button">
                          {t("transactions.addToFolder")}
                        </button>
                      ) : (
                        <span className="button--ghost button--wide transaction-actions__placeholder" aria-hidden="true" />
                      )}
                      {/* Card payments only: nothing else reaches the
                          Analytics donut or a budget, so the button would
                          promise an effect the user could never see. */}
                      {tx.status === "COMPLETED" && tx.type === "CARD_PAYMENT" ? (
                        <button
                          aria-label={t("transactions.changeCategory")}
                          className="button--ghost button--round"
                          onClick={() => openCategoryModal(tx)}
                          title={t("transactions.changeCategory")}
                          type="button"
                        >
                          <Plus size={16} />
                        </button>
                      ) : (
                        <span className="button--ghost button--round transaction-actions__placeholder" aria-hidden="true" />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {transactions.length > TRANSACTIONS_PER_PAGE && (
          <div
            style={{
              alignItems: "center",
              display: "flex",
              flexWrap: "wrap",
              gap: "0.6rem",
              justifyContent: "space-between",
              marginTop: "1rem",
            }}
          >
            <span className="eyebrow">
              {t("transactions.showingRange", { first: firstVisibleTransaction, last: lastVisibleTransaction, total: transactions.length })}
            </span>
            <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
              <button
                type="button"
                className="button--ghost"
                aria-label={t("transactions.previousPage")}
                disabled={currentTransactionsPage === 1}
                onClick={() => setTransactionsPage((value) => Math.max(1, value - 1))}
                style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
              >
                <ChevronLeft size={16} aria-hidden="true" />
              </button>
              {transactionPageNumbers.map((pageNumber) => (
                <button
                  key={pageNumber}
                  type="button"
                  className={pageNumber === currentTransactionsPage ? undefined : "button--ghost"}
                  aria-label={t("transactions.goToPage", { page: pageNumber })}
                  aria-current={pageNumber === currentTransactionsPage ? "page" : undefined}
                  onClick={() => setTransactionsPage(pageNumber)}
                  style={{ minWidth: 40, padding: "0.65rem 0.75rem" }}
                >
                  {pageNumber}
                </button>
              ))}
              <button
                type="button"
                className="button--ghost"
                aria-label={t("transactions.nextPage")}
                disabled={currentTransactionsPage === transactionPageCount}
                onClick={() => setTransactionsPage((value) => Math.min(transactionPageCount, value + 1))}
                style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
              >
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </section>
    </section>
  );
}

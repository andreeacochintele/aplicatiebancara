import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, apiRequest } from "../api/apiClient";
import { BILL_SPLIT_CHANGED_EVENT } from "../events";
import { useAuth } from "../hooks/useAuth";
import type { Beneficiary, BillSplit, Transaction, TransactionFolder, Wallet } from "../types";

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

function formatAmount(transaction: Transaction, userWalletIds: Set<string>): string {
  const sign = isIncomingOnly(transaction, userWalletIds) ? "+" : "-";
  return `${sign}${transaction.amount} ${transaction.currency}`;
}

function formatTransactionType(transaction: Transaction, userWalletIds: Set<string>): string {
  const description = transaction.description?.toLowerCase() ?? "";
  if (description.includes("loan") && description.includes("disbursement") && isIncomingOnly(transaction, userWalletIds)) {
    return "Bank -> user";
  }
  if (transaction.type === "LOAN_PAYMENT") {
    return "User -> bank";
  }
  return transaction.type.replaceAll("_", " ");
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
      const [nextTransactions, nextWallets, nextBillSplits] = await Promise.all([
        apiRequest<Transaction[]>("/transactions", { token: accessToken }),
        apiRequest<Wallet[]>("/wallets", { token: accessToken }).catch(() => []),
        apiRequest<BillSplit[]>("/payments/bill-splits", { token: accessToken }).catch(() => []),
      ]);
      setTransactions(nextTransactions);
      setWallets(nextWallets);
      setBillSplits(nextBillSplits);
      await loadTransactionFolders();
    } catch (err) {
      setTransactions([]);
      setTransactionsError(err instanceof ApiError ? err.message : "Could not load transactions.");
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
      setFolderError(`Folder title must be ${FOLDER_NAME_MAX_LENGTH} characters or less.`);
      return;
    }
    if (folderDescription.length > FOLDER_DESCRIPTION_MAX_LENGTH) {
      setFolderError(`Folder description must be ${FOLDER_DESCRIPTION_MAX_LENGTH} characters or less.`);
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
      setFolderNotice("Folder created.");
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : "Could not create folder");
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
      setFolderNotice("Transaction added to folder.");
      await loadTransactionFolders();
    } catch (err) {
      setFolderError(err instanceof ApiError ? err.message : "Could not add transaction to folder");
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
      setSplitError("Choose at least one person.");
      return;
    }
    if (requestedPercent <= 0 || requestedPercent > 100) {
      setSplitError("Requested shares must be more than 0% and at most 100%.");
      return;
    }
    if (
      splitParticipants.some(
        (participant) => !participant.name.trim() || (!participant.participant_user_id.trim() && !participant.phone.trim()),
      )
    ) {
      setSplitError("Each request needs the recipient name and phone number.");
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
            ? `Split: ${baseSplitDescription(splitTransaction.description)}`
            : "Split bill",
          total_amount: splitTransaction.amount,
          currency: splitTransaction.currency,
          source_transaction_id: splitTransaction.id,
          description: "Created from transaction split bill",
          participants: splitParticipants.map((participant) => ({
            participant_user_id: participant.participant_user_id.trim() || null,
            name: participant.name.trim(),
            phone: participant.phone.trim() || null,
            percent: participant.percent,
          })),
        },
      });
      setSplitNotice("Split bill requests sent.");
      setSplitTransaction(null);
      setSplitParticipants([]);
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not create split bill");
    } finally {
      setSplitSubmitting(false);
    }
  }

  async function paySplitRequest(split: BillSplit, participantId: string) {
    if (!accessToken) return;
    const sourceWallet = wallets.find((wallet) => wallet.currency === split.currency);
    if (!sourceWallet) {
      setSplitError(`No ${split.currency} wallet available for this payment.`);
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
      setSplitNotice("Split bill paid.");
      await refreshTransactionsData();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not pay split bill");
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
      setSplitNotice("Split bill refused.");
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not refuse split bill");
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
      setSplitNotice("Split bill cancelled.");
      await loadBillSplits();
    } catch (err) {
      setSplitError(err instanceof ApiError ? err.message : "Could not cancel split bill");
    } finally {
      setSplitActionId(null);
    }
  }

  return (
    <section>
      <div className="transactions-header">
        <h2>Transactions</h2>
        <button className="button--ghost button--wide" onClick={() => void refreshTransactionsData()} type="button">
          Refresh
        </button>
      </div>
      {transactionsError && <p className="status-line status-line--error">{transactionsError}</p>}
      {splitNotice && <p className="status-line">{splitNotice}</p>}
      {pendingSplitRequests.length > 0 && (
        <div className="transaction-split-requests">
          {pendingSplitRequests.map(({ split, participant }) => (
            <div className="transaction-split-request" key={participant.id}>
              <div>
                <span className="eyebrow">Split bill request</span>
                <strong>{split.title}</strong>
                <span>
                  {participant.name} asks for {participant.amount} {split.currency}
                </span>
              </div>
              <div className="transaction-split-request__actions">
                <button
                  className="button--wide"
                  disabled={splitActionId === participant.id}
                  onClick={() => paySplitRequest(split, participant.id)}
                  type="button"
                >
                  Pay
                </button>
                <button
                  className="button--wide button--ghost"
                  disabled={splitActionId === participant.id}
                  onClick={() => refuseSplitRequest(split, participant.id)}
                  type="button"
                >
                  Refuse
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
                  <span className="eyebrow">Your split</span>
                  <strong>{split.title}</strong>
                  <span>
                    {paidCount} of {split.participants.length} paid &middot; {split.total_amount} {split.currency}
                  </span>
                </div>
                <div className="transaction-split-request__actions">
                  <button
                    className="button--wide button--ghost"
                    disabled={splitActionId === split.id}
                    onClick={() => cancelOwnedSplit(split)}
                    type="button"
                  >
                    {splitActionId === split.id ? "Cancelling..." : "Cancel"}
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
            <span className="eyebrow">Split bill</span>
            <button className="button--ghost" type="button" onClick={() => setSplitTransaction(null)}>
              Close
            </button>
          </div>
          <div className="split-builder__summary">
            <strong>{splitTransaction.description || splitTransaction.type}</strong>
            <span>
              {splitTransaction.amount} {splitTransaction.currency} on{" "}
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
            <p className="status-line">No internal beneficiaries yet. Add one manually below.</p>
          )}
          <div className="form-actions">
            <button className="button--ghost" onClick={splitEqually} type="button">
              Split equally
            </button>
            <button className="button--ghost" onClick={addManualParticipant} type="button">
              Add person
            </button>
          </div>
          <div className="split-participant-list">
            {splitParticipants.map((participant) => (
              <div className="split-participant-row" key={participant.key}>
                <label>
                  Recipient name
                  <input
                    onChange={(event) => updateSplitParticipant(participant.key, { name: event.target.value })}
                    placeholder="Maria Dinu"
                    value={participant.name}
                  />
                </label>
                <label>
                  Phone number
                  <input
                    onChange={(event) => updateSplitParticipant(participant.key, { phone: event.target.value })}
                    placeholder="+40700000101"
                    value={participant.phone}
                  />
                </label>
                <label>
                  Percent
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
                  Remove
                </button>
              </div>
            ))}
          </div>
          {splitParticipants.length > 0 && (
            <p className="status-line">
              Requested total: {moneyFromPercent(splitTransaction.amount, String(splitParticipants.reduce((sum, participant) => sum + toNumber(participant.percent), 0)))}{" "}
              {splitTransaction.currency}
            </p>
          )}
          {splitError && <p className="status-line status-line--error">{splitError}</p>}
          <button disabled={splitSubmitting || splitParticipants.length === 0} onClick={submitSplitBill} type="button">
            {splitSubmitting ? "Sending..." : "Send money requests"}
          </button>
        </div>
      ) : null}
      {folderTransaction ? (
        <div className="folder-modal-backdrop" role="presentation">
          <section className="tile folder-modal" role="dialog" aria-modal="true" aria-label="Add transaction to folder">
            <div className="tile__header">
              <div>
                <span className="eyebrow">Add to folder</span>
                <h2>{folderTransaction.description || folderTransaction.type}</h2>
              </div>
              <button className="button--ghost" onClick={() => setFolderTransaction(null)} type="button">
                Close
              </button>
            </div>

            <div className="folder-modal__create">
              <label>
                Folder title
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
                Description
                <input
                  maxLength={FOLDER_DESCRIPTION_MAX_LENGTH}
                  onChange={(event) => setFolderDescription(event.target.value)}
                  placeholder="Optional"
                  value={folderDescription}
                />
                <span className="field-hint">
                  {folderDescription.length}/{FOLDER_DESCRIPTION_MAX_LENGTH}
                </span>
              </label>
              <button className="button--wide" disabled={folderCreating || !folderName.trim()} onClick={createFolder} type="button">
                {folderCreating ? "Creating..." : "Create new folder"}
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
                        <small>{folder.description || `${folder.items.length} transaction(s)`}</small>
                      </span>
                      <div className="folder-choice__actions">
                        <span>Added</span>
                        <button
                          className="button--ghost button--wide"
                          onClick={() => navigate(`/payments?tab=folders&folder=${folder.id}`)}
                          type="button"
                        >
                          Go to folder
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
                      <small>{folder.description || `${folder.items.length} transaction(s)`}</small>
                    </span>
                    <span>Add</span>
                  </button>
                );
              })}
              {transactionFolders.length === 0 && (
                <div className="empty-state">No folders yet. Create one above.</div>
              )}
            </div>
          </section>
        </div>
      ) : null}
      <section className="tile transactions-table-card">
        {transactionsLoading ? (
          <div className="empty-state">Loading transactions...</div>
        ) : transactions.length === 0 ? (
          <div className="empty-state">No transactions found for {user?.first_name ?? "this user"}.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Description</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {visibleTransactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{new Date(tx.created_at).toLocaleString()}</td>
                  <td>{formatTransactionType(tx, userWalletIds)}</td>
                  <td>{tx.description}</td>
                  <td className={isIncomingOnly(tx, userWalletIds) ? "transaction-amount--in" : "transaction-amount--out"}>
                    {formatAmount(tx, userWalletIds)}
                  </td>
                  <td>{tx.status}</td>
                  <td>
                    <div className="transaction-actions">
                      {tx.status === "COMPLETED" && (
                        <>
                          {isIncomingOnly(tx, userWalletIds) ? (
                            <span />
                          ) : (
                            <button className="button--ghost button--wide" onClick={() => openSplit(tx)} type="button">
                              Split bill
                            </button>
                          )}
                          <button className="button--ghost button--wide" onClick={() => openFolderModal(tx)} type="button">
                            Add to folder
                          </button>
                        </>
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
              Showing {firstVisibleTransaction}-{lastVisibleTransaction} of {transactions.length}
            </span>
            <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
              <button
                type="button"
                className="button--ghost"
                aria-label="Previous transactions page"
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
                  aria-label={`Go to transactions page ${pageNumber}`}
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
                aria-label="Next transactions page"
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

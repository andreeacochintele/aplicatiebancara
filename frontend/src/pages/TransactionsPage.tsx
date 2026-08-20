import { useEffect, useState } from "react";

import { ApiError, apiRequest } from "../api/apiClient";
import { BILL_SPLIT_CHANGED_EVENT } from "../events";
import { useAuth } from "../hooks/useAuth";
import type { Beneficiary, BillSplit, Transaction, Wallet } from "../types";

interface SplitParticipantDraft {
  key: string;
  name: string;
  participant_user_id: string;
  phone: string;
  percent: string;
}

function formatAmount(transaction: Transaction, userWalletIds: Set<string>): string {
  const isIncoming = transaction.destination_wallet_id ? userWalletIds.has(transaction.destination_wallet_id) : false;
  const isOutgoing = transaction.source_wallet_id ? userWalletIds.has(transaction.source_wallet_id) : false;
  const sign = isIncoming && !isOutgoing ? "+" : "-";
  return `${sign}${transaction.amount} ${transaction.currency}`;
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
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [billSplits, setBillSplits] = useState<BillSplit[]>([]);
  const [splitTransaction, setSplitTransaction] = useState<Transaction | null>(null);
  const [splitParticipants, setSplitParticipants] = useState<SplitParticipantDraft[]>([]);
  const [splitNotice, setSplitNotice] = useState<string | null>(null);
  const [splitError, setSplitError] = useState<string | null>(null);
  const [splitSubmitting, setSplitSubmitting] = useState(false);
  const [splitActionId, setSplitActionId] = useState<string | null>(null);

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

  const userWalletIds = new Set(wallets.map((wallet) => wallet.id));
  const internalBeneficiaries = beneficiaries.filter((beneficiary) => beneficiary.beneficiary_user_id);
  const pendingSplitRequests = billSplits.flatMap((split) =>
    split.participants
      .filter((participant) => participant.status === "PENDING" && participant.participant_user_id === user?.id)
      .map((participant) => ({ split, participant })),
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
    const [nextTransactions, nextWallets, nextBillSplits] = await Promise.all([
      apiRequest<Transaction[]>("/transactions", { token: accessToken }).catch(() => []),
      apiRequest<Wallet[]>("/wallets", { token: accessToken }).catch(() => []),
      apiRequest<BillSplit[]>("/payments/bill-splits", { token: accessToken }).catch(() => []),
    ]);
    setTransactions(nextTransactions);
    setWallets(nextWallets);
    setBillSplits(nextBillSplits);
  }

  function openSplit(transaction: Transaction) {
    setSplitTransaction(transaction);
    setSplitParticipants([]);
    setSplitNotice(null);
    setSplitError(null);
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
      setSplitError("Each request needs a name and phone number.");
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

  return (
    <section>
      <h2>Transactions</h2>
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
                  Person
                  <input
                    onChange={(event) => updateSplitParticipant(participant.key, { name: event.target.value })}
                    placeholder="Name"
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
          {transactions.map((tx) => (
            <tr key={tx.id}>
              <td>{new Date(tx.created_at).toLocaleString()}</td>
              <td>{tx.type}</td>
              <td>{tx.description}</td>
              <td>{formatAmount(tx, userWalletIds)}</td>
              <td>{tx.status}</td>
              <td>
                <button className="button--ghost" onClick={() => openSplit(tx)} type="button">
                  Split bill
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

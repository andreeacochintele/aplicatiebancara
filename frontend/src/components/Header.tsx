import { Bell } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError, apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { BillSplit, Wallet } from "../types";

const PAGE_INFO: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "Dashboard", subtitle: "Personal banking overview" },
  "/wallets": { title: "Wallets", subtitle: "One wallet per currency" },
  "/cards": { title: "Cards", subtitle: "Debit, credit and one-time cards" },
  "/payments": { title: "Payments", subtitle: "Transfer, phone, QR and scheduled" },
  "/transactions": { title: "Transactions", subtitle: "Search, filter and group into folders" },
  "/statements": { title: "Statements", subtitle: "Opening/closing balance and CSV/PDF export" },
  "/analytics": { title: "Analytics", subtitle: "Spending, budgets and goals" },
  "/rewards": { title: "Rewards", subtitle: "Cashback and merchant offers" },
  "/credit": { title: "Credit & Loans", subtitle: "Score, instalments and simulation" },
  "/assistant": { title: "Assistant", subtitle: "Orchestrator over specialised agents" },
  "/profile": { title: "Profile", subtitle: "Account details" },
  "/admin": { title: "Admin Dashboard", subtitle: "Operations overview" },
};

function initials(firstName?: string, lastName?: string): string {
  return `${firstName?.[0] ?? ""}${lastName?.[0] ?? ""}`.toUpperCase();
}

export function Header() {
  const { user, accessToken, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const page = PAGE_INFO[location.pathname];
  const [billSplits, setBillSplits] = useState<BillSplit[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notificationError, setNotificationError] = useState<string | null>(null);
  const [actionId, setActionId] = useState<string | null>(null);

  const pendingSplitRequests = billSplits.flatMap((split) =>
    split.participants
      .filter((participant) => participant.status === "PENDING" && participant.participant_user_id === user?.id)
      .map((participant) => ({ split, participant })),
  );

  useEffect(() => {
    if (!accessToken) return;
    void loadNotifications();
  }, [accessToken, location.pathname]);

  async function loadNotifications() {
    if (!accessToken) return;
    try {
      const [nextSplits, nextWallets] = await Promise.all([
        apiRequest<BillSplit[]>("/payments/bill-splits", { token: accessToken }),
        apiRequest<Wallet[]>("/wallets", { token: accessToken }),
      ]);
      setBillSplits(nextSplits);
      setWallets(nextWallets);
      setNotificationError(null);
    } catch {
      setBillSplits([]);
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  async function payRequest(split: BillSplit, participantId: string) {
    if (!accessToken) return;
    const sourceWallet = wallets.find((wallet) => wallet.currency === split.currency);
    if (!sourceWallet) {
      setNotificationError(`No ${split.currency} wallet available.`);
      return;
    }
    setActionId(participantId);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/participants/${participantId}/pay`, {
        method: "POST",
        token: accessToken,
        body: { source_wallet_id: sourceWallet.id },
      });
      await loadNotifications();
    } catch (err) {
      setNotificationError(err instanceof ApiError ? err.message : "Could not pay request");
    } finally {
      setActionId(null);
    }
  }

  async function refuseRequest(split: BillSplit, participantId: string) {
    if (!accessToken) return;
    setActionId(participantId);
    try {
      await apiRequest<BillSplit>(`/payments/bill-splits/${split.id}/participants/${participantId}/decline`, {
        method: "POST",
        token: accessToken,
      });
      await loadNotifications();
    } catch (err) {
      setNotificationError(err instanceof ApiError ? err.message : "Could not refuse request");
    } finally {
      setActionId(null);
    }
  }

  return (
    <header className="header aurora-header">
      <span className="header__title">{page?.title ?? "Banking App"}</span>
      {page && <span className="header__subtitle">{page.subtitle}</span>}
      <div className="header__meta">
        <button
          aria-label="Notifications"
          className="aurora-bell"
          onClick={() => setNotificationsOpen((open) => !open)}
          type="button"
        >
          <Bell size={16} />
          {pendingSplitRequests.length > 0 && <span className="notification-badge">{pendingSplitRequests.length}</span>}
        </button>
        {notificationsOpen && (
          <div className="notification-panel">
            <div className="notification-panel__header">
              <strong>Notifications</strong>
              <button className="button--ghost" onClick={() => void loadNotifications()} type="button">
                Refresh
              </button>
            </div>
            {notificationError && <p className="status-line status-line--error">{notificationError}</p>}
            {pendingSplitRequests.length === 0 ? (
              <p className="empty-state">No pending requests.</p>
            ) : (
              pendingSplitRequests.map(({ split, participant }) => (
                <div className="notification-item" key={participant.id}>
                  <span className="eyebrow">Split bill</span>
                  <strong>{split.title}</strong>
                  <span>
                    {participant.amount} {split.currency}
                  </span>
                  <div className="notification-item__actions">
                    <button
                      disabled={actionId === participant.id}
                      onClick={() => payRequest(split, participant.id)}
                      type="button"
                    >
                      Pay
                    </button>
                    <button
                      className="button--ghost"
                      disabled={actionId === participant.id}
                      onClick={() => refuseRequest(split, participant.id)}
                      type="button"
                    >
                      Refuse
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
        {user && (
          <div className="header__user">
            {user.role === "ADMIN" && <span className="tag tag--accent">ADMIN</span>}
            {user.user_type === "BUSINESS" && <span className="tag tag--outline">BUSINESS</span>}
            <span className="avatar">{initials(user.first_name, user.last_name)}</span>
            <span>
              {user.first_name} {user.last_name}
            </span>
          </div>
        )}
        <button onClick={handleLogout}>Logout</button>
      </div>
    </header>
  );
}

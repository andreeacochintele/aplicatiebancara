import { Bell, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError, apiRequest } from "../api/apiClient";
import { BILL_SPLIT_CHANGED_EVENT } from "../events";
import { useAuth } from "../hooks/useAuth";
import type { BillSplit, Notification, Wallet } from "../types";
import { ThemeToggle } from "./ThemeToggle";

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
  "/business/export": { title: "Transaction Export", subtitle: "Business accounts only · CSV/XLSX export" },
  "/admin": { title: "Admin Dashboard", subtitle: "Operations overview" },
  "/admin/credit": { title: "Credit & Loans", subtitle: "Applications, documents and credit score review" },
  "/admin/fraud": { title: "Fraud Review", subtitle: "Deterministic engine · human decision" },
};

const HEADER_NOTIFICATIONS_PER_PAGE = 4;

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
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notificationError, setNotificationError] = useState<string | null>(null);
  const [actionId, setActionId] = useState<string | null>(null);
  const [dismissingId, setDismissingId] = useState<string | null>(null);
  const [notificationPage, setNotificationPage] = useState(1);

  const pendingSplitRequests = billSplits.flatMap((split) =>
    split.participants
      .filter((participant) => participant.status === "PENDING" && participant.participant_user_id === user?.id)
      .map((participant) => ({ split, participant })),
  );
  const notificationItemCount = pendingSplitRequests.length + notifications.length;

  useEffect(() => {
    if (!accessToken) return;
    void loadNotifications();
  }, [accessToken, location.pathname]);

  useEffect(() => {
    setNotificationPage((currentPage) => {
      const maxPage = Math.max(1, Math.ceil(notificationItemCount / HEADER_NOTIFICATIONS_PER_PAGE));
      return Math.min(currentPage, maxPage);
    });
  }, [notificationItemCount]);

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
    try {
      const nextNotifications = await apiRequest<Notification[]>("/notifications?unread_only=true", {
        token: accessToken,
      });
      setNotifications(nextNotifications);
    } catch {
      setNotifications([]);
    }
  }

  async function dismissNotification(notificationId: string) {
    if (!accessToken) return;
    setDismissingId(notificationId);
    try {
      await apiRequest<Notification>(`/notifications/${notificationId}/read`, {
        method: "POST",
        token: accessToken,
      });
      setNotifications((current) => current.filter((n) => n.id !== notificationId));
    } catch (err) {
      setNotificationError(err instanceof ApiError ? err.message : "Could not dismiss notification");
    } finally {
      setDismissingId(null);
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
      window.dispatchEvent(new Event(BILL_SPLIT_CHANGED_EVENT));
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
      window.dispatchEvent(new Event(BILL_SPLIT_CHANGED_EVENT));
    } catch (err) {
      setNotificationError(err instanceof ApiError ? err.message : "Could not refuse request");
    } finally {
      setActionId(null);
    }
  }

  const notificationPanelItems = [
    ...notifications.map((notification) => ({ kind: "notification" as const, id: notification.id, notification })),
    ...pendingSplitRequests.map(({ split, participant }) => ({
      kind: "split" as const,
      id: participant.id,
      participant,
      split,
    })),
  ];
  const notificationPageCount = Math.max(1, Math.ceil(notificationPanelItems.length / HEADER_NOTIFICATIONS_PER_PAGE));
  const currentNotificationPage = Math.min(notificationPage, notificationPageCount);
  const notificationPageStart = (currentNotificationPage - 1) * HEADER_NOTIFICATIONS_PER_PAGE;
  const visibleNotificationPanelItems = notificationPanelItems.slice(
    notificationPageStart,
    notificationPageStart + HEADER_NOTIFICATIONS_PER_PAGE,
  );
  const firstPanelItem = notificationPanelItems.length === 0 ? 0 : notificationPageStart + 1;
  const lastPanelItem = Math.min(notificationPageStart + HEADER_NOTIFICATIONS_PER_PAGE, notificationPanelItems.length);
  const visiblePanelNotifications = visibleNotificationPanelItems.flatMap((item) =>
    item.kind === "notification" ? [item.notification] : [],
  );
  const visiblePanelSplitRequests = visibleNotificationPanelItems.flatMap((item) =>
    item.kind === "split" ? [{ split: item.split, participant: item.participant }] : [],
  );

  return (
    <header className="header aurora-header">
      <span className="header__title">{page?.title ?? "Banking App"}</span>
      {page && <span className="header__subtitle">{page.subtitle}</span>}
      <div className="header__meta">
        <ThemeToggle />
        <button
          aria-label="Notifications"
          className="aurora-bell"
          onClick={() => setNotificationsOpen((open) => !open)}
          type="button"
        >
          <Bell size={16} />
          {notificationItemCount > 0 && (
            <span className="notification-badge">{notificationItemCount}</span>
          )}
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
            {notificationItemCount === 0 ? (
              <p className="empty-state">No pending requests.</p>
            ) : (
              <>
                {visiblePanelNotifications.map((notification) => (
                  <div className="notification-item" key={notification.id}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                      <div>
                        <span className="eyebrow">{notification.title}</span>
                        <strong style={{ display: "block", fontWeight: 400 }}>{notification.message}</strong>
                      </div>
                      <button
                        className="button--ghost"
                        aria-label="Dismiss notification"
                        disabled={dismissingId === notification.id}
                        onClick={() => dismissNotification(notification.id)}
                        type="button"
                        style={{ flexShrink: 0 }}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
                {visiblePanelSplitRequests.map(({ split, participant }) => (
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
                ))}
                {notificationPanelItems.length > HEADER_NOTIFICATIONS_PER_PAGE && (
                  <div
                    className="notification-item__actions"
                    style={{ borderTop: "1px solid var(--color-divider)", paddingTop: "0.7rem" }}
                  >
                    <span className="eyebrow">
                      {firstPanelItem}-{lastPanelItem} of {notificationPanelItems.length}
                    </span>
                    <div style={{ display: "flex", gap: "0.35rem" }}>
                      <button
                        type="button"
                        className="button--ghost"
                        aria-label="Previous notification page"
                        disabled={currentNotificationPage === 1}
                        onClick={() => setNotificationPage((value) => Math.max(1, value - 1))}
                        style={{ minWidth: 36, padding: "0.45rem 0.55rem" }}
                      >
                        <ChevronLeft size={14} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        className="button--ghost"
                        aria-label="Next notification page"
                        disabled={currentNotificationPage === notificationPageCount}
                        onClick={() => setNotificationPage((value) => Math.min(notificationPageCount, value + 1))}
                        style={{ minWidth: 36, padding: "0.45rem 0.55rem" }}
                      >
                        <ChevronRight size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                )}
              </>
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

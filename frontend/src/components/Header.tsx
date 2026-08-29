import { Bell, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError, apiRequest } from "../api/apiClient";
import { BILL_SPLIT_CHANGED_EVENT } from "../events";
import { useAuth } from "../hooks/useAuth";
import type { BillSplit, Notification, Wallet } from "../types";
import { LanguageToggle } from "./LanguageToggle";
import { ThemeToggle } from "./ThemeToggle";

const PAGE_INFO: Record<string, { titleKey: string; subtitleKey: string }> = {
  "/dashboard": { titleKey: "pageInfo.dashboard.title", subtitleKey: "pageInfo.dashboard.subtitle" },
  "/wallets": { titleKey: "pageInfo.wallets.title", subtitleKey: "pageInfo.wallets.subtitle" },
  "/cards": { titleKey: "pageInfo.cards.title", subtitleKey: "pageInfo.cards.subtitle" },
  "/payments": { titleKey: "pageInfo.payments.title", subtitleKey: "pageInfo.payments.subtitle" },
  "/transactions": { titleKey: "pageInfo.transactions.title", subtitleKey: "pageInfo.transactions.subtitle" },
  "/statements": { titleKey: "pageInfo.statements.title", subtitleKey: "pageInfo.statements.subtitle" },
  "/analytics": { titleKey: "pageInfo.analytics.title", subtitleKey: "pageInfo.analytics.subtitle" },
  "/rewards": { titleKey: "pageInfo.rewards.title", subtitleKey: "pageInfo.rewards.subtitle" },
  "/credit": { titleKey: "pageInfo.credit.title", subtitleKey: "pageInfo.credit.subtitle" },
  "/assistant": { titleKey: "pageInfo.assistant.title", subtitleKey: "pageInfo.assistant.subtitle" },
  "/profile": { titleKey: "pageInfo.profile.title", subtitleKey: "pageInfo.profile.subtitle" },
  "/business/export": { titleKey: "pageInfo.businessExport.title", subtitleKey: "pageInfo.businessExport.subtitle" },
  "/business/profile": { titleKey: "pageInfo.businessProfile.title", subtitleKey: "pageInfo.businessProfile.subtitle" },
  "/admin": { titleKey: "pageInfo.admin.title", subtitleKey: "pageInfo.admin.subtitle" },
  "/admin/credit": { titleKey: "pageInfo.adminCredit.title", subtitleKey: "pageInfo.adminCredit.subtitle" },
  "/admin/fraud": { titleKey: "pageInfo.adminFraud.title", subtitleKey: "pageInfo.adminFraud.subtitle" },
  "/admin/audit-log": { titleKey: "pageInfo.adminAuditLog.title", subtitleKey: "pageInfo.adminAuditLog.subtitle" },
};

const HEADER_NOTIFICATIONS_PER_PAGE = 4;

function initials(firstName?: string, lastName?: string): string {
  return `${firstName?.[0] ?? ""}${lastName?.[0] ?? ""}`.toUpperCase();
}

export function Header() {
  const { t } = useTranslation();
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
  const [activeCompanyName, setActiveCompanyName] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || user?.user_type !== "BUSINESS") {
      setActiveCompanyName(null);
      return;
    }
    apiRequest<{ company_name: string } | null>("/business/profile", { token: accessToken })
      .then((profile) => setActiveCompanyName(profile?.company_name ?? null))
      .catch(() => setActiveCompanyName(null));
  }, [accessToken, user?.user_type]);

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
      setNotificationError(err instanceof ApiError ? err.message : t("header.couldNotDismissNotification"));
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
      setNotificationError(t("header.noWalletAvailable", { currency: split.currency }));
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
      setNotificationError(err instanceof ApiError ? err.message : t("header.couldNotPayRequest"));
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
      setNotificationError(err instanceof ApiError ? err.message : t("header.couldNotRefuseRequest"));
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
    <header className="header easyb-header">
      <span className="header__title">{page ? t(page.titleKey) : t("common.appName")}</span>
      {page && <span className="header__subtitle">{t(page.subtitleKey)}</span>}
      <div className="header__meta">
        <LanguageToggle />
        <ThemeToggle />
        <button
          aria-label={t("header.notifications")}
          className="easyb-bell"
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
              <strong>{t("header.notifications")}</strong>
              <button className="button--ghost" onClick={() => void loadNotifications()} type="button">
                {t("header.refresh")}
              </button>
            </div>
            {notificationError && <p className="status-line status-line--error">{notificationError}</p>}
            {notificationItemCount === 0 ? (
              <p className="empty-state">{t("header.noPendingRequests")}</p>
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
                        aria-label={t("header.dismissNotification")}
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
                    <span className="eyebrow">{t("header.splitBill")}</span>
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
                        {t("header.pay")}
                      </button>
                      <button
                        className="button--ghost"
                        disabled={actionId === participant.id}
                        onClick={() => refuseRequest(split, participant.id)}
                        type="button"
                      >
                        {t("header.refuse")}
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
                      {t("header.pageRange", { first: firstPanelItem, last: lastPanelItem, total: notificationPanelItems.length })}
                    </span>
                    <div style={{ display: "flex", gap: "0.35rem" }}>
                      <button
                        type="button"
                        className="button--ghost"
                        aria-label={t("header.previousPage")}
                        disabled={currentNotificationPage === 1}
                        onClick={() => setNotificationPage((value) => Math.max(1, value - 1))}
                        style={{ minWidth: 36, padding: "0.45rem 0.55rem" }}
                      >
                        <ChevronLeft size={14} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        className="button--ghost"
                        aria-label={t("header.nextPage")}
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
            {user.role === "ADMIN" && <span className="tag tag--accent">{t("header.admin")}</span>}
            {user.user_type === "BUSINESS" && (
              <button
                type="button"
                className="tag tag--outline header__company-switch"
                onClick={() => navigate("/business/profile")}
                title={t("header.switchCompany")}
              >
                {activeCompanyName ?? t("header.business")}
              </button>
            )}
            <span className="avatar">{initials(user.first_name, user.last_name)}</span>
            <span>
              {user.first_name} {user.last_name}
            </span>
          </div>
        )}
        <button onClick={handleLogout}>{t("header.logout")}</button>
      </div>
    </header>
  );
}

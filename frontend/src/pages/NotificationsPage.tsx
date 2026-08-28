import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Notification } from "../types";

const NOTIFICATIONS_PER_PAGE = 5;

// type is free-text on the backend (any module can add its own) — labels for
// the ones we know about, humanized fallback for anything else.
function typeLabel(type: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  return t(`notifications.type.${type}`, {
    defaultValue: type.charAt(0) + type.slice(1).toLowerCase().replace(/_/g, " "),
  });
}

export function NotificationsPage() {
  const { t } = useTranslation();
  const { accessToken } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [markingAll, setMarkingAll] = useState(false);
  const [page, setPage] = useState(1);

  function loadNotifications() {
    if (!accessToken) return;
    apiRequest<Notification[]>("/notifications", { token: accessToken })
      .then(setNotifications)
      .catch(() => setNotifications([]));
  }

  useEffect(loadNotifications, [accessToken]);

  useEffect(() => {
    setPage((currentPage) => {
      const maxPage = Math.max(1, Math.ceil(notifications.length / NOTIFICATIONS_PER_PAGE));
      return Math.min(currentPage, maxPage);
    });
  }, [notifications.length]);

  async function markRead(notification: Notification) {
    if (!accessToken || notification.is_read) return;
    setBusyId(notification.id);
    setError(null);
    try {
      const updated = await apiRequest<Notification>(`/notifications/${notification.id}/read`, {
        method: "POST",
        token: accessToken,
      });
      setNotifications((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("notifications.couldNotMarkRead"));
    } finally {
      setBusyId(null);
    }
  }

  async function markAllRead() {
    if (!accessToken) return;
    const unread = notifications.filter((n) => !n.is_read);
    if (unread.length === 0) return;
    setMarkingAll(true);
    setError(null);
    try {
      // No bulk endpoint — mark each unread notification individually.
      await Promise.all(
        unread.map((n) => apiRequest<Notification>(`/notifications/${n.id}/read`, { method: "POST", token: accessToken })),
      );
      setNotifications((current) => current.map((item) => ({ ...item, is_read: true })));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("notifications.couldNotMarkAllRead"));
      loadNotifications();
    } finally {
      setMarkingAll(false);
    }
  }

  const unreadCount = notifications.filter((notification) => !notification.is_read).length;
  const totalPages = Math.max(1, Math.ceil(notifications.length / NOTIFICATIONS_PER_PAGE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * NOTIFICATIONS_PER_PAGE;
  const visibleNotifications = notifications.slice(pageStart, pageStart + NOTIFICATIONS_PER_PAGE);
  const pageNumbers = Array.from({ length: totalPages }, (_, index) => index + 1);
  const firstVisible = notifications.length === 0 ? 0 : pageStart + 1;
  const lastVisible = Math.min(pageStart + NOTIFICATIONS_PER_PAGE, notifications.length);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{unreadCount > 0 ? t("notifications.unreadCount", { count: unreadCount }) : t("notifications.allCaughtUp")}</span>
          <button
            onClick={markAllRead}
            disabled={markingAll || unreadCount === 0}
            style={{ marginLeft: "auto" }}
          >
            {t("notifications.markAllAsRead")}
          </button>
        </div>
        {error && <p role="alert">{error}</p>}

        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginTop: "0.75rem" }}>
          {visibleNotifications.map((notification) => (
            <div
              key={notification.id}
              className="tile"
              style={{
                boxShadow: notification.is_read ? undefined : "inset 0 0 0 1px var(--color-accent)",
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
                justifyContent: "space-between",
              }}
            >
              <div>
                <span className={`tag ${notification.is_read ? "tag--neutral" : "tag--accent"}`}>
                  {typeLabel(notification.type, t)}
                </span>
                <div style={{ fontWeight: 600, marginTop: "0.4rem" }}>{notification.title}</div>
                <div style={{ color: "var(--color-text-muted)" }}>{notification.message}</div>
                <div className="eyebrow" style={{ marginTop: "0.3rem" }}>
                  {new Date(notification.created_at).toLocaleString()}
                </div>
              </div>
              {!notification.is_read && (
                <button onClick={() => markRead(notification)} disabled={busyId === notification.id}>
                  {t("notifications.markAsRead")}
                </button>
              )}
            </div>
          ))}
          {notifications.length === 0 && <p>{t("notifications.noNotificationsYet")}</p>}
        </div>

        {notifications.length > NOTIFICATIONS_PER_PAGE && (
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
              {t("notifications.showingRange", { first: firstVisible, last: lastVisible, total: notifications.length })}
            </span>
            <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
              <button
                type="button"
                className="button--ghost"
                aria-label={t("notifications.previousPage")}
                disabled={currentPage === 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
              >
                <ChevronLeft size={16} aria-hidden="true" />
              </button>
              {pageNumbers.map((pageNumber) => (
                <button
                  key={pageNumber}
                  type="button"
                  className={pageNumber === currentPage ? undefined : "button--ghost"}
                  aria-label={t("notifications.goToPage", { page: pageNumber })}
                  aria-current={pageNumber === currentPage ? "page" : undefined}
                  onClick={() => setPage(pageNumber)}
                  style={{ minWidth: 40, padding: "0.65rem 0.75rem" }}
                >
                  {pageNumber}
                </button>
              ))}
              <button
                type="button"
                className="button--ghost"
                aria-label={t("notifications.nextPage")}
                disabled={currentPage === totalPages}
                onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                style={{ minWidth: 44, padding: "0.65rem 0.75rem" }}
              >
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

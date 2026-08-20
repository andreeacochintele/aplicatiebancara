import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Notification } from "../types";

const TYPE_LABEL: Record<Notification["type"], string> = {
  TRANSACTION: "Transaction",
  FRAUD: "Fraud",
  PAYMENT_REMINDER: "Payment reminder",
  CASHBACK: "Cashback",
  CREDIT: "Credit",
  SPLIT_BILL: "Split bill",
  SYSTEM: "System",
};

export function NotificationsPage() {
  const { accessToken } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [markingAll, setMarkingAll] = useState(false);

  function loadNotifications() {
    if (!accessToken) return;
    apiRequest<Notification[]>("/notifications", { token: accessToken })
      .then(setNotifications)
      .catch(() => setNotifications([]));
  }

  useEffect(loadNotifications, [accessToken]);

  async function markRead(notification: Notification) {
    if (!accessToken || notification.is_read) return;
    setBusyId(notification.id);
    setError(null);
    try {
      const updated = await apiRequest<Notification>(`/notifications/${notification.id}/read`, {
        method: "PATCH",
        token: accessToken,
      });
      setNotifications((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not mark notification as read");
    } finally {
      setBusyId(null);
    }
  }

  async function markAllRead() {
    if (!accessToken) return;
    setMarkingAll(true);
    setError(null);
    try {
      await apiRequest("/notifications/read-all", { method: "PATCH", token: accessToken });
      setNotifications((current) => current.map((item) => ({ ...item, is_read: true })));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not mark notifications as read");
    } finally {
      setMarkingAll(false);
    }
  }

  const unreadCount = notifications.filter((notification) => !notification.is_read).length;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{unreadCount > 0 ? `${unreadCount} unread` : "All caught up"}</span>
          <button
            onClick={markAllRead}
            disabled={markingAll || unreadCount === 0}
            style={{ marginLeft: "auto" }}
          >
            Mark all as read
          </button>
        </div>
        {error && <p role="alert">{error}</p>}

        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginTop: "0.75rem" }}>
          {notifications.map((notification) => (
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
                  {TYPE_LABEL[notification.type]}
                </span>
                <div style={{ fontWeight: 600, marginTop: "0.4rem" }}>{notification.title}</div>
                <div style={{ color: "var(--color-text-muted)" }}>{notification.message}</div>
                <div className="eyebrow" style={{ marginTop: "0.3rem" }}>
                  {new Date(notification.created_at).toLocaleString()}
                </div>
              </div>
              {!notification.is_read && (
                <button onClick={() => markRead(notification)} disabled={busyId === notification.id}>
                  Mark as read
                </button>
              )}
            </div>
          ))}
          {notifications.length === 0 && <p>No notifications yet.</p>}
        </div>
      </div>
    </section>
  );
}

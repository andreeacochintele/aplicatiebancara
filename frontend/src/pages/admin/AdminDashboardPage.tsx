import { Landmark, ShieldAlert, UserPlus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type { CreditApplication, CreditApplicationStatus, FraudCaseStatus, FraudCaseSummary, User } from "../../types";

interface OperationCard {
  to: string;
  icon: typeof Landmark;
  title: string;
  description: string;
  pendingCount: number | null;
  pendingLabel: string;
}

const CREDIT_STATUS_COLORS: Record<CreditApplicationStatus, string> = {
  DRAFT: "#94a3b8",
  PENDING: "#f59e0b",
  APPROVED: "#10b981",
  REJECTED: "#ef4444",
};

const FRAUD_STATUS_COLORS: Record<FraudCaseStatus, string> = {
  PENDING_REVIEW: "#f59e0b",
  APPROVED: "#10b981",
  REJECTED: "#ef4444",
};

function todayMinus(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function withinRange(isoTimestamp: string, dateFrom: string, dateTo: string): boolean {
  const day = isoTimestamp.slice(0, 10);
  return day >= dateFrom && day <= dateTo;
}

function statusBreakdown<T extends string>(items: T[], colors: Record<T, string>) {
  const counts = new Map<T, number>();
  for (const item of items) {
    counts.set(item, (counts.get(item) ?? 0) + 1);
  }
  return [...counts.entries()].map(([status, value]) => ({
    key: status,
    name: status.replaceAll("_", " "),
    value,
    color: colors[status],
  }));
}

function StatusDonut({ title, data, total }: { title: string; data: ReturnType<typeof statusBreakdown>; total: number }) {
  const { t } = useTranslation();
  return (
    <div className="easyb-card">
      <div className="easyb-section-header">
        <div>
          <div className="easyb-eyebrow">{t("admin.statusBreakdown")}</div>
          <h2>{title}</h2>
        </div>
      </div>
      {data.length > 0 ? (
        <>
          <div className="easyb-donut-wrap">
            <ResponsiveContainer width="100%" height={150}>
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={68} paddingAngle={2} stroke="none">
                  {data.map((item) => (
                    <Cell key={item.key} fill={item.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, name: string) => [value, name]}
                  contentStyle={{ borderRadius: 10, border: "1px solid var(--easyb-border)", fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="easyb-donut-center">
              <div className="easyb-donut-total">{total}</div>
              <div className="easyb-donut-label">{t("admin.total")}</div>
            </div>
          </div>
          <div className="easyb-legend">
            {data.map((item) => (
              <div className="easyb-legend-row" key={item.key}>
                <span className="easyb-legend-dot" style={{ background: item.color }} />
                <span className="easyb-legend-name">{item.name}</span>
                <span className="easyb-legend-pct">{total > 0 ? Math.round((item.value / total) * 100) : 0}%</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="easyb-tx-meta">{t("admin.noDataYet")}</p>
      )}
    </div>
  );
}

export function AdminDashboardPage() {
  const { t } = useTranslation();
  const { accessToken, logout, user } = useAuth();
  const [applications, setApplications] = useState<CreditApplication[] | null>(null);
  const [cases, setCases] = useState<FraudCaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState(todayMinus(30));
  const [dateTo, setDateTo] = useState(todayMinus(0));
  const [admins, setAdmins] = useState<User[] | null>(null);
  const [promoteEmail, setPromoteEmail] = useState("");
  const [promoting, setPromoting] = useState(false);
  const [promoteError, setPromoteError] = useState<string | null>(null);
  const [promoteSuccess, setPromoteSuccess] = useState<string | null>(null);

  async function loadAdmins() {
    if (!accessToken) return;
    try {
      const response = await apiRequest<User[]>("/users/admin/admins", { token: accessToken });
      setAdmins(response);
    } catch {
      setAdmins([]);
    }
  }

  async function promoteToAdmin() {
    if (!accessToken || !promoteEmail.trim()) return;
    setPromoting(true);
    setPromoteError(null);
    setPromoteSuccess(null);
    try {
      const promoted = await apiRequest<User>("/users/admin/promote", {
        method: "POST",
        token: accessToken,
        body: { email: promoteEmail.trim() },
      });
      setPromoteSuccess(t("admin.promoteSuccess", { name: `${promoted.first_name} ${promoted.last_name}` }));
      setPromoteEmail("");
      await loadAdmins();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setPromoteError(err instanceof ApiError ? err.message : t("admin.couldNotPromote"));
    } finally {
      setPromoting(false);
    }
  }

  useEffect(() => {
    if (!accessToken || user?.role !== "ADMIN") return;
    void loadAdmins();
    (async () => {
      try {
        const response = await apiRequest<CreditApplication[]>("/credit/admin/applications", { token: accessToken });
        setApplications(response);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setApplications([]);
      }
      try {
        const response = await apiRequest<FraudCaseSummary[]>("/fraud/cases", { token: accessToken });
        setCases(response);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setError(err instanceof ApiError ? err.message : t("admin.couldNotLoadOverview"));
        setCases([]);
      }
    })();
  }, [accessToken, logout, user?.role]);

  const pendingCredit = useMemo(
    () => applications?.filter((a) => a.status === "PENDING" || a.status === "DRAFT").length ?? null,
    [applications],
  );
  const pendingFraud = useMemo(
    () => cases?.filter((c) => c.status === "PENDING_REVIEW").length ?? null,
    [cases],
  );
  const applicationsInRange = useMemo(
    () => applications?.filter((a) => withinRange(a.created_at, dateFrom, dateTo)) ?? [],
    [applications, dateFrom, dateTo],
  );
  const casesInRange = useMemo(
    () => cases?.filter((c) => withinRange(c.created_at, dateFrom, dateTo)) ?? [],
    [cases, dateFrom, dateTo],
  );
  const creditBreakdown = useMemo(
    () => statusBreakdown(applicationsInRange.map((a) => a.status), CREDIT_STATUS_COLORS),
    [applicationsInRange],
  );
  const fraudBreakdown = useMemo(
    () => statusBreakdown(casesInRange.map((c) => c.status), FRAUD_STATUS_COLORS),
    [casesInRange],
  );

  if (user?.role !== "ADMIN") {
    return (
      <section className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.adminDashboard")}</span>
        </div>
        <div className="card-empty">{t("admin.adminPrivilegesRequired")}</div>
      </section>
    );
  }

  const cards: OperationCard[] = [
    {
      to: "/admin/credit",
      icon: Landmark,
      title: t("admin.creditAndLoans"),
      description: t("admin.creditAndLoansDescription"),
      pendingCount: pendingCredit,
      pendingLabel: t("admin.pendingApplications"),
    },
    {
      to: "/admin/fraud",
      icon: ShieldAlert,
      title: t("admin.fraudReview"),
      description: t("admin.fraudReviewDescription"),
      pendingCount: pendingFraud,
      pendingLabel: t("admin.pendingCases"),
    },
  ];

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {error && <p style={{ color: "var(--color-warning)", margin: 0 }}>{error}</p>}
      <div className="admin-overview-grid">
        {cards.map((card) => (
          <Link to={card.to} key={card.to} className="tile admin-overview-card">
            <div className="admin-overview-card__icon">
              <card.icon size={22} />
            </div>
            <div className="admin-overview-card__body">
              <strong>{card.title}</strong>
              <span>{card.description}</span>
            </div>
            <span className="tag tag--neutral">
              {card.pendingCount === null ? "..." : card.pendingCount} {card.pendingLabel}
            </span>
          </Link>
        ))}
      </div>
      <div className="admin-applications-toolbar">
        <label>
          <span className="eyebrow">{t("admin.from")}</span>
          <input type="date" value={dateFrom} max={dateTo} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label>
          <span className="eyebrow">{t("admin.to")}</span>
          <input type="date" value={dateTo} min={dateFrom} onChange={(e) => setDateTo(e.target.value)} />
        </label>
      </div>
      <div className="easyb-analytics-grid">
        <StatusDonut title={t("admin.creditApplications")} data={creditBreakdown} total={applicationsInRange.length} />
        <StatusDonut title={t("admin.fraudCases")} data={fraudBreakdown} total={casesInRange.length} />
      </div>

      <div className="tile" style={{ maxWidth: 520 }}>
        <div className="tile__header">
          <span className="eyebrow">{t("admin.admins")}</span>
        </div>
        {admins === null ? (
          <p className="easyb-tx-meta">{t("admin.loadingAdmins")}</p>
        ) : (
          <ul style={{ listStyle: "none", margin: "0 0 1rem", padding: 0, display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {admins.map((admin) => (
              <li key={admin.id} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem" }}>
                <span>
                  {admin.first_name} {admin.last_name}
                </span>
                <span style={{ color: "var(--color-text-muted)" }}>{admin.email}</span>
              </li>
            ))}
            {admins.length === 0 && <li className="easyb-tx-meta">{t("admin.noAdminsYet")}</li>}
          </ul>
        )}
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={{ flex: 1, minWidth: 220 }}>
            <span className="eyebrow">{t("admin.promoteByEmail")}</span>
            <input
              type="email"
              value={promoteEmail}
              onChange={(e) => setPromoteEmail(e.target.value)}
              placeholder="user@example.com"
            />
          </label>
          <button type="button" onClick={() => void promoteToAdmin()} disabled={promoting || !promoteEmail.trim()}>
            <UserPlus size={14} style={{ verticalAlign: -2, marginRight: 4 }} aria-hidden="true" />
            {promoting ? t("admin.promoting") : t("admin.promote")}
          </button>
        </div>
        {promoteError && <p role="alert" style={{ color: "var(--color-warning)", margin: "0.6rem 0 0" }}>{promoteError}</p>}
        {promoteSuccess && <p role="status" style={{ color: "var(--color-success)", margin: "0.6rem 0 0" }}>{promoteSuccess}</p>}
      </div>
    </section>
  );
}

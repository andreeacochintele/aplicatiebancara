import { Landmark, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";
import type { CreditApplication, CreditApplicationStatus, FraudCaseStatus, FraudCaseSummary } from "../../types";

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
  return (
    <div className="aurora-card">
      <div className="aurora-section-header">
        <div>
          <div className="aurora-eyebrow">Status breakdown</div>
          <h2>{title}</h2>
        </div>
      </div>
      {data.length > 0 ? (
        <>
          <div className="aurora-donut-wrap">
            <ResponsiveContainer width="100%" height={150}>
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={68} paddingAngle={2} stroke="none">
                  {data.map((item) => (
                    <Cell key={item.key} fill={item.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, name: string) => [value, name]}
                  contentStyle={{ borderRadius: 10, border: "1px solid var(--aurora-border)", fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="aurora-donut-center">
              <div className="aurora-donut-total">{total}</div>
              <div className="aurora-donut-label">total</div>
            </div>
          </div>
          <div className="aurora-legend">
            {data.map((item) => (
              <div className="aurora-legend-row" key={item.key}>
                <span className="aurora-legend-dot" style={{ background: item.color }} />
                <span className="aurora-legend-name">{item.name}</span>
                <span className="aurora-legend-pct">{total > 0 ? Math.round((item.value / total) * 100) : 0}%</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="aurora-tx-meta">No data yet.</p>
      )}
    </div>
  );
}

export function AdminDashboardPage() {
  const { accessToken, logout, user } = useAuth();
  const [applications, setApplications] = useState<CreditApplication[] | null>(null);
  const [cases, setCases] = useState<FraudCaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || user?.role !== "ADMIN") return;
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
        setError(err instanceof ApiError ? err.message : "Could not load operations overview.");
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
  const creditBreakdown = useMemo(
    () => statusBreakdown(applications?.map((a) => a.status) ?? [], CREDIT_STATUS_COLORS),
    [applications],
  );
  const fraudBreakdown = useMemo(
    () => statusBreakdown(cases?.map((c) => c.status) ?? [], FRAUD_STATUS_COLORS),
    [cases],
  );

  if (user?.role !== "ADMIN") {
    return (
      <section className="tile">
        <div className="tile__header">
          <span className="eyebrow">Admin dashboard</span>
        </div>
        <div className="card-empty">Admin privileges required.</div>
      </section>
    );
  }

  const cards: OperationCard[] = [
    {
      to: "/admin/credit",
      icon: Landmark,
      title: "Credit & Loans",
      description: "Review loan and credit card applications, documents and credit scores.",
      pendingCount: pendingCredit,
      pendingLabel: "pending applications",
    },
    {
      to: "/admin/fraud",
      icon: ShieldAlert,
      title: "Fraud Review",
      description: "Investigate held transactions flagged by the fraud engine and decide their outcome.",
      pendingCount: pendingFraud,
      pendingLabel: "pending cases",
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
      <div className="aurora-analytics-grid">
        <StatusDonut title="Credit applications" data={creditBreakdown} total={applications?.length ?? 0} />
        <StatusDonut title="Fraud cases" data={fraudBreakdown} total={cases?.length ?? 0} />
      </div>
    </section>
  );
}

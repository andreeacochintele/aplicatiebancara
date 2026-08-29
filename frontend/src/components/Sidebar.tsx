import {
  LayoutDashboard, Wallet, CreditCard, Send, Receipt, FileText,
  PieChart, Gift, Landmark, Sparkles, Bell, UserRound, ShieldAlert, Briefcase, Building2, LayoutGrid, ScrollText, type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { BrandMark } from "./BrandMark";
import { useAuth } from "../hooks/useAuth";

interface NavItem {
  to: string;
  labelKey: string;
  icon: LucideIcon;
}

const BANKING_ITEMS: NavItem[] = [
  { to: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { to: "/wallets", labelKey: "nav.wallets", icon: Wallet },
  { to: "/cards", labelKey: "nav.cards", icon: CreditCard },
  { to: "/payments", labelKey: "nav.payments", icon: Send },
  { to: "/transactions", labelKey: "nav.transactions", icon: Receipt },
  { to: "/statements", labelKey: "nav.statements", icon: FileText },
];

const INTELLIGENCE_ITEMS: NavItem[] = [
  { to: "/analytics", labelKey: "nav.analytics", icon: PieChart },
  { to: "/rewards", labelKey: "nav.rewards", icon: Gift },
  { to: "/credit", labelKey: "nav.credit", icon: Landmark },
  { to: "/assistant", labelKey: "nav.assistant", icon: Sparkles },
];

const ACCOUNT_ITEMS: NavItem[] = [
  { to: "/notifications", labelKey: "nav.notifications", icon: Bell },
  { to: "/profile", labelKey: "nav.profile", icon: UserRound },
];

const OPERATIONS_ITEMS: NavItem[] = [
  { to: "/admin", labelKey: "nav.dashboard", icon: LayoutGrid },
  { to: "/admin/credit", labelKey: "nav.creditAndLoans", icon: Landmark },
  { to: "/admin/fraud", labelKey: "nav.fraudReview", icon: ShieldAlert },
  { to: "/admin/audit-log", labelKey: "nav.auditLog", icon: ScrollText },
];

function NavGroup({ label, items }: { label: string; items: NavItem[] }) {
  const { t } = useTranslation();
  return (
    <div className="sidebar__group">
      <div className="sidebar__group-label">{label}</div>
      <ul className="sidebar__nav">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} end className={({ isActive }) => (isActive ? "active" : "")}>
              <item.icon size={17} />
              {t(item.labelKey)}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sidebar() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const isBusiness = user?.user_type === "BUSINESS";
  // Cashback still earns correctly on a business account's card spend, but
  // the points/referral loyalty framing on this page is personal-banking
  // shaped — hidden for business accounts as a deliberate product choice,
  // not because anything about it is broken there.
  // Credit hidden too: the score is an explicit 300-850 personal FICO-style
  // number and the loan products (Mortgage/Auto/Student/Home Improvement/
  // Personal Loan) are all personal life-event loans — none of it fits a
  // business account. Unlike Rewards, there's no working part to keep (a
  // real business credit-card product would need its own build).
  const intelligenceItems = isBusiness
    ? INTELLIGENCE_ITEMS.filter((item) => item.to !== "/rewards" && item.to !== "/credit")
    : INTELLIGENCE_ITEMS;

  return (
    <nav className="sidebar easyb-sidebar">
      <div className="easyb-brand">
        <BrandMark className="easyb-brand-mark" size={56} />
        <span className="easyb-brand-name">{t("common.appName")}</span>
      </div>
      {isAdmin ? (
        <NavGroup label={t("nav.operations")} items={OPERATIONS_ITEMS} />
      ) : (
        <>
          <NavGroup label={t("nav.banking")} items={BANKING_ITEMS} />
          <NavGroup label={t("nav.intelligence")} items={intelligenceItems} />
          <NavGroup label={t("nav.account")} items={ACCOUNT_ITEMS} />
          {isBusiness && (
            <NavGroup
              label={t("nav.business")}
              items={[
                { to: "/business/export", labelKey: "nav.businessExport", icon: Briefcase },
                { to: "/business/profile", labelKey: "nav.businessProfile", icon: Building2 },
              ]}
            />
          )}
        </>
      )}
    </nav>
  );
}

import {
  LayoutDashboard, Wallet, CreditCard, Send, Receipt, FileText,
  PieChart, Gift, Landmark, Sparkles, Bell, UserRound, ShieldAlert, Briefcase, Building2, LayoutGrid, type LucideIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { BrandMark } from "./BrandMark";
import { useAuth } from "../hooks/useAuth";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const BANKING_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/wallets", label: "Wallets", icon: Wallet },
  { to: "/cards", label: "Cards", icon: CreditCard },
  { to: "/payments", label: "Payments", icon: Send },
  { to: "/transactions", label: "Transactions", icon: Receipt },
  { to: "/statements", label: "Statements", icon: FileText },
];

const INTELLIGENCE_ITEMS: NavItem[] = [
  { to: "/analytics", label: "Analytics", icon: PieChart },
  { to: "/rewards", label: "Rewards", icon: Gift },
  { to: "/credit", label: "Credit", icon: Landmark },
  { to: "/assistant", label: "Assistant", icon: Sparkles },
];

const ACCOUNT_ITEMS: NavItem[] = [
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/profile", label: "Profile", icon: UserRound },
];

const OPERATIONS_ITEMS: NavItem[] = [
  { to: "/admin", label: "Dashboard", icon: LayoutGrid },
  { to: "/admin/credit", label: "Credit & Loans", icon: Landmark },
  { to: "/admin/fraud", label: "Fraud Review", icon: ShieldAlert },
];

function NavGroup({ label, items }: { label: string; items: NavItem[] }) {
  return (
    <div className="sidebar__group">
      <div className="sidebar__group-label">{label}</div>
      <ul className="sidebar__nav">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} end className={({ isActive }) => (isActive ? "active" : "")}>
              <item.icon size={17} />
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sidebar() {
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
        <span className="easyb-brand-name">EasyB</span>
      </div>
      {isAdmin ? (
        <NavGroup label="Operations" items={OPERATIONS_ITEMS} />
      ) : (
        <>
          <NavGroup label="Banking" items={BANKING_ITEMS} />
          <NavGroup label="Intelligence" items={intelligenceItems} />
          <NavGroup label="Account" items={ACCOUNT_ITEMS} />
          {isBusiness && (
            <NavGroup
              label="Business"
              items={[
                { to: "/business/export", label: "Transaction Export", icon: Briefcase },
                { to: "/business/profile", label: "Company Profile", icon: Building2 },
              ]}
            />
          )}
        </>
      )}
    </nav>
  );
}

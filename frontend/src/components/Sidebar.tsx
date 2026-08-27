import {
  LayoutDashboard, Wallet, CreditCard, Send, Receipt, FileText,
  PieChart, Gift, Landmark, Sparkles, Bell, UserRound, ShieldAlert, Briefcase, LayoutGrid, type LucideIcon,
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

  return (
    <nav className="sidebar aurora-sidebar">
      <div className="aurora-brand">
        <BrandMark className="aurora-brand-mark" size={56} />
        <span className="aurora-brand-name">EasyB</span>
      </div>
      {isAdmin ? (
        <NavGroup label="Operations" items={OPERATIONS_ITEMS} />
      ) : (
        <>
          <NavGroup label="Banking" items={BANKING_ITEMS} />
          <NavGroup label="Intelligence" items={INTELLIGENCE_ITEMS} />
          <NavGroup label="Account" items={ACCOUNT_ITEMS} />
          {user?.user_type === "BUSINESS" && (
            <NavGroup
              label="Business"
              items={[{ to: "/business/export", label: "Transaction Export", icon: Briefcase }]}
            />
          )}
        </>
      )}
    </nav>
  );
}

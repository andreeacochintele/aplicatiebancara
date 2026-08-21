import {
  LayoutDashboard, Wallet, CreditCard, Send, Receipt, FileText,
  PieChart, Gift, Landmark, Sparkles, Bell, UserRound, ShieldCheck, type LucideIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";

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

function NavGroup({ label, items }: { label: string; items: NavItem[] }) {
  return (
    <div className="sidebar__group">
      <div className="sidebar__group-label">{label}</div>
      <ul className="sidebar__nav">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} className={({ isActive }) => (isActive ? "active" : "")}>
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

  return (
    <nav className="sidebar aurora-sidebar">
      <div className="aurora-brand">
        <span className="aurora-brand-mark" />
        <span className="aurora-brand-name">Banking App</span>
      </div>
      <NavGroup label="Banking" items={BANKING_ITEMS} />
      <NavGroup label="Intelligence" items={INTELLIGENCE_ITEMS} />
      <NavGroup label="Account" items={ACCOUNT_ITEMS} />
      {user?.role === "ADMIN" && (
        <NavGroup label="Operations" items={[{ to: "/admin", label: "Admin Dashboard", icon: ShieldCheck }]} />
      )}
    </nav>
  );
}

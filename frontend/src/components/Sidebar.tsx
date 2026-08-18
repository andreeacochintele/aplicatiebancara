import { NavLink } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

interface NavItem {
  to: string;
  label: string;
}

const BANKING_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/wallets", label: "Wallets" },
  { to: "/cards", label: "Cards" },
  { to: "/payments", label: "Payments" },
  { to: "/transactions", label: "Transactions" },
  { to: "/statements", label: "Statements" },
];

const INTELLIGENCE_ITEMS: NavItem[] = [
  { to: "/analytics", label: "Analytics" },
  { to: "/rewards", label: "Rewards" },
  { to: "/credit", label: "Credit" },
  { to: "/assistant", label: "Assistant" },
];

const ACCOUNT_ITEMS: NavItem[] = [{ to: "/profile", label: "Profile" }];

function NavGroup({ label, items }: { label: string; items: NavItem[] }) {
  return (
    <div className="sidebar__group">
      <div className="sidebar__group-label">{label}</div>
      <ul className="sidebar__nav">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} className={({ isActive }) => (isActive ? "active" : "")}>
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
    <nav className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__brand-mark">B</span>
        Banking App
      </div>
      <NavGroup label="Banking" items={BANKING_ITEMS} />
      <NavGroup label="Intelligence" items={INTELLIGENCE_ITEMS} />
      <NavGroup label="Account" items={ACCOUNT_ITEMS} />
      {user?.role === "ADMIN" && <NavGroup label="Operations" items={[{ to: "/admin", label: "Admin Dashboard" }]} />}
    </nav>
  );
}

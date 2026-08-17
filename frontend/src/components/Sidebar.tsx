import { NavLink } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/wallets", label: "Wallets" },
  { to: "/cards", label: "Cards" },
  { to: "/payments", label: "Payments" },
  { to: "/transactions", label: "Transactions" },
  { to: "/analytics", label: "Analytics" },
  { to: "/rewards", label: "Rewards" },
  { to: "/credit", label: "Credit" },
  { to: "/assistant", label: "Assistant" },
  { to: "/profile", label: "Profile" },
];

export function Sidebar() {
  const { user } = useAuth();

  return (
    <nav className="sidebar">
      <div className="sidebar__brand">Banking App</div>
      <ul className="sidebar__nav">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} className={({ isActive }) => (isActive ? "active" : "")}>
              {item.label}
            </NavLink>
          </li>
        ))}
        {user?.role === "ADMIN" && (
          <li>
            <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
              Admin
            </NavLink>
          </li>
        )}
      </ul>
    </nav>
  );
}

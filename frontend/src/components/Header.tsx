import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

const PAGE_INFO: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "Dashboard", subtitle: "Personal banking overview" },
  "/wallets": { title: "Wallets", subtitle: "One wallet per currency" },
  "/cards": { title: "Cards", subtitle: "Debit, credit and one-time cards" },
  "/payments": { title: "Payments", subtitle: "Transfer, phone, QR and scheduled" },
  "/transactions": { title: "Transactions", subtitle: "Search, filter and group into folders" },
  "/analytics": { title: "Analytics", subtitle: "Spending, budgets and goals" },
  "/rewards": { title: "Rewards", subtitle: "Cashback and merchant offers" },
  "/credit": { title: "Credit & Loans", subtitle: "Score, instalments and simulation" },
  "/assistant": { title: "Assistant", subtitle: "Orchestrator over specialised agents" },
  "/profile": { title: "Profile", subtitle: "Account details" },
  "/admin": { title: "Admin Dashboard", subtitle: "Operations overview" },
};

function initials(firstName?: string, lastName?: string): string {
  return `${firstName?.[0] ?? ""}${lastName?.[0] ?? ""}`.toUpperCase();
}

export function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const page = PAGE_INFO[location.pathname];

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="header">
      <span className="header__title">{page?.title ?? "Banking App"}</span>
      {page && <span className="header__subtitle">{page.subtitle}</span>}
      <div className="header__meta">
        {user && (
          <div className="header__user">
            {user.role === "ADMIN" && <span className="tag tag--accent">ADMIN</span>}
            {user.user_type === "BUSINESS" && <span className="tag tag--outline">BUSINESS</span>}
            <span className="avatar">{initials(user.first_name, user.last_name)}</span>
            <span>
              {user.first_name} {user.last_name}
            </span>
          </div>
        )}
        <button onClick={handleLogout}>Logout</button>
      </div>
    </header>
  );
}

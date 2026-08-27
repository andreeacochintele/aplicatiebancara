import { Outlet } from "react-router-dom";

import { ThemeToggle } from "../components/ThemeToggle";

export function AuthLayout() {
  return (
    <div className="auth-layout">
      <div className="auth-layout__card">
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <ThemeToggle />
        </div>
        <h1>Banking App</h1>
        <Outlet />
      </div>
    </div>
  );
}

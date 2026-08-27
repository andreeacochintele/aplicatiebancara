import { Outlet } from "react-router-dom";

import { ThemeToggle } from "../components/ThemeToggle";

export function AuthLayout() {
  return (
    <div className="auth-layout">
      <div className="auth-layout__card">
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <ThemeToggle />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <img src="/logo.svg" alt="" style={{ width: 32, height: 32, borderRadius: 9 }} />
          <h1 style={{ margin: 0 }}>EasyB</h1>
        </div>
        <Outlet />
      </div>
    </div>
  );
}

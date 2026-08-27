import { Outlet } from "react-router-dom";

import { BrandMark } from "../components/BrandMark";
import { ThemeToggle } from "../components/ThemeToggle";

export function AuthLayout() {
  return (
    <div className="auth-layout">
      <div className="auth-layout__card">
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <ThemeToggle />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <BrandMark size={72} />
          <h1 style={{ margin: 0 }}>EasyB</h1>
        </div>
        <Outlet />
      </div>
    </div>
  );
}

import { Outlet } from "react-router-dom";

import { BrandMark } from "../components/BrandMark";
import { HiveModeToggle } from "../components/HiveModeToggle";
import { LanguageToggle } from "../components/LanguageToggle";
import { ThemeToggle } from "../components/ThemeToggle";

export function AuthLayout() {
  return (
    <div className="auth-layout">
      <div className="auth-layout__card">
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <LanguageToggle />
          <ThemeToggle />
          <HiveModeToggle />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <BrandMark className="easyb-brand-mark" size={72} />
          <h1 style={{ margin: 0 }}>EasyB</h1>
        </div>
        <Outlet />
      </div>
    </div>
  );
}

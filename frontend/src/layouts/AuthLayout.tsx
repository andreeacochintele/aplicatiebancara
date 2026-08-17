import { Outlet } from "react-router-dom";

export function AuthLayout() {
  return (
    <div className="auth-layout">
      <div className="auth-layout__card">
        <h1>Banking App</h1>
        <Outlet />
      </div>
    </div>
  );
}

import { Outlet } from "react-router-dom";

import { Header } from "../components/Header";
import { IdleWarning } from "../components/IdleWarning";
import { Sidebar } from "../components/Sidebar";

export function MainLayout() {
  return (
    <div className="app-shell easyb-shell">
      <Sidebar />
      <div className="app-shell__main">
        <Header />
        <main className="app-shell__content">
          <Outlet />
        </main>
      </div>
      <IdleWarning />
    </div>
  );
}

import { Navigate, type RouteObject } from "react-router-dom";

import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthLayout } from "./layouts/AuthLayout";
import { MainLayout } from "./layouts/MainLayout";
import { AdminDashboardPage } from "./pages/admin/AdminDashboardPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { CardsPage } from "./pages/CardsPage";
import { CreditPage } from "./pages/CreditPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PaymentsPage } from "./pages/PaymentsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RewardsPage } from "./pages/RewardsPage";
import { StatementsPage } from "./pages/StatementsPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { WalletsPage } from "./pages/WalletsPage";

export const routes: RouteObject[] = [
  {
    element: <AuthLayout />,
    children: [{ path: "/login", element: <LoginPage /> }],
  },
  {
    path: "/onboarding",
    element: (
      <ProtectedRoute requireOnboarding={false}>
        <OnboardingPage />
      </ProtectedRoute>
    ),
  },
  {
    element: (
      <ProtectedRoute>
        <MainLayout />
      </ProtectedRoute>
    ),
    children: [
      { path: "/dashboard", element: <DashboardPage /> },
      { path: "/wallets", element: <WalletsPage /> },
      { path: "/cards", element: <CardsPage /> },
      { path: "/payments", element: <PaymentsPage /> },
      { path: "/transactions", element: <TransactionsPage /> },
      { path: "/statements", element: <StatementsPage /> },
      { path: "/analytics", element: <AnalyticsPage /> },
      { path: "/rewards", element: <RewardsPage /> },
      { path: "/credit", element: <CreditPage /> },
      { path: "/assistant", element: <AssistantPage /> },
      { path: "/profile", element: <ProfilePage /> },
      { path: "/admin", element: <AdminDashboardPage /> },
    ],
  },
  { path: "/", element: <Navigate to="/dashboard" replace /> },
  { path: "*", element: <Navigate to="/dashboard" replace /> },
];

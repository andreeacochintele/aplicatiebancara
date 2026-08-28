import type { RouteObject } from "react-router-dom";

import { HomeRedirect } from "./components/HomeRedirect";
import { InviteRedirect } from "./components/InviteRedirect";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthLayout } from "./layouts/AuthLayout";
import { MainLayout } from "./layouts/MainLayout";
import { AdminDashboardPage } from "./pages/admin/AdminDashboardPage";
import { CreditReviewPage } from "./pages/admin/CreditReviewPage";
import { FraudReviewPage } from "./pages/admin/FraudReviewPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { BusinessExportPage } from "./pages/BusinessExportPage";
import { BusinessProfilePage } from "./pages/BusinessProfilePage";
import { CardsPage } from "./pages/CardsPage";
import { CreditPage } from "./pages/CreditPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { NotificationsPage } from "./pages/NotificationsPage";
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
  { path: "/invite/:code", element: <InviteRedirect /> },
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
      {
        path: "/rewards",
        element: (
          <ProtectedRoute blockUserType="BUSINESS">
            <RewardsPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "/credit",
        element: (
          <ProtectedRoute blockUserType="BUSINESS">
            <CreditPage />
          </ProtectedRoute>
        ),
      },
      { path: "/assistant", element: <AssistantPage /> },
      { path: "/notifications", element: <NotificationsPage /> },
      { path: "/profile", element: <ProfilePage /> },
      { path: "/business/export", element: <BusinessExportPage /> },
      { path: "/business/profile", element: <BusinessProfilePage /> },
      {
        path: "/admin",
        element: (
          <ProtectedRoute requireRole="ADMIN">
            <AdminDashboardPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "/admin/credit",
        element: (
          <ProtectedRoute requireRole="ADMIN">
            <CreditReviewPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "/admin/fraud",
        element: (
          <ProtectedRoute requireRole="ADMIN">
            <FraudReviewPage />
          </ProtectedRoute>
        ),
      },
    ],
  },
  { path: "/", element: <HomeRedirect /> },
  { path: "*", element: <HomeRedirect /> },
];

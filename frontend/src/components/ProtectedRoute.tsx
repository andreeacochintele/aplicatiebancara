import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

export function ProtectedRoute({
  children,
  requireOnboarding = true,
  requireRole,
  blockUserType,
}: {
  children: ReactNode;
  requireOnboarding?: boolean;
  requireRole?: "USER" | "ADMIN";
  blockUserType?: "PERSONAL" | "BUSINESS";
}) {
  const { isAuthenticated, onboardingCompleted, user } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (requireRole && user?.role !== requireRole) {
    return <Navigate to="/dashboard" replace />;
  }
  if (blockUserType && user?.user_type === blockUserType) {
    return <Navigate to="/dashboard" replace />;
  }
  if (requireOnboarding && onboardingCompleted === false) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}

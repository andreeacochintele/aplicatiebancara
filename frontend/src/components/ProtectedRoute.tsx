import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

export function ProtectedRoute({
  children,
  requireOnboarding = true,
}: {
  children: ReactNode;
  requireOnboarding?: boolean;
}) {
  const { isAuthenticated, onboardingCompleted } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (requireOnboarding && onboardingCompleted === false) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}

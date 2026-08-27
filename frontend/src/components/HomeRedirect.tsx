import { Navigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

/** Sends an authenticated admin to the admin area instead of the personal
 * dashboard — admins don't get a Dashboard/Wallets/etc. nav entry at all
 * (see Sidebar), so landing there would be a dead end. */
export function HomeRedirect() {
  const { user, isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <Navigate to={user?.role === "ADMIN" ? "/admin" : "/dashboard"} replace />;
}

import { Navigate, useParams } from "react-router-dom";

// Landing spot for the "Your invite link" shown on the Rewards page
// (/invite/<referral_code>) -- forwards straight to registration with the
// code pre-filled via ?ref=, since whoever clicks a friend's invite link
// almost certainly doesn't have an account yet.
export function InviteRedirect() {
  const { code } = useParams<{ code: string }>();
  return <Navigate to={`/login?ref=${encodeURIComponent(code ?? "")}`} replace />;
}

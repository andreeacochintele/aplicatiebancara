import { useEffect, useState } from "react";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Wallet } from "../types";

export function DashboardPage() {
  const { user, accessToken } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
  }, [accessToken]);

  return (
    <section>
      <h2>Welcome, {user?.first_name}</h2>
      <h3>Your wallets</h3>
      <ul>
        {wallets.map((wallet) => (
          <li key={wallet.id}>
            {wallet.currency} — {wallet.available_balance} {wallet.is_main ? "(main)" : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

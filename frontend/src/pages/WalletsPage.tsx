import { useEffect, useState } from "react";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Wallet } from "../types";

export function WalletsPage() {
  const { accessToken } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
  }, [accessToken]);

  return (
    <section>
      <h2>Wallets</h2>
      <table>
        <thead>
          <tr>
            <th>Currency</th>
            <th>Available</th>
            <th>Reserved</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {wallets.map((wallet) => (
            <tr key={wallet.id}>
              <td>
                {wallet.currency} {wallet.is_main && "(main)"}
              </td>
              <td>{wallet.available_balance}</td>
              <td>{wallet.reserved_balance}</td>
              <td>{wallet.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

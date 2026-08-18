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
    <section className="tile">
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
                {wallet.currency} {wallet.is_main && <span className="tag tag--accent">MAIN</span>}
              </td>
              <td>{wallet.available_balance}</td>
              <td>{wallet.reserved_balance}</td>
              <td>
                <span className="tag tag--neutral">{wallet.status}</span>
              </td>
            </tr>
          ))}
          {wallets.length === 0 && (
            <tr>
              <td colSpan={4}>No wallets yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

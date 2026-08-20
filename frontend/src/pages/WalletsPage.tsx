import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { FXQuote, Wallet } from "../types";

export function WalletsPage() {
  const { accessToken } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [amount, setAmount] = useState("100");
  const [quote, setQuote] = useState<FXQuote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [settingMainId, setSettingMainId] = useState<string | null>(null);

  function loadWallets() {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
  }

  useEffect(loadWallets, [accessToken]);

  async function setMainWallet(walletId: string) {
    if (!accessToken || settingMainId) return;
    setSettingMainId(walletId);
    setError(null);
    try {
      await apiRequest(`/wallets/${walletId}/set-main`, { method: "PATCH", token: accessToken });
      loadWallets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not set main wallet");
    } finally {
      setSettingMainId(null);
    }
  }

  useEffect(() => {
    if (wallets.length < 2) return;
    if (!sourceId) setSourceId(wallets[0].id);
    if (!targetId) {
      const other = wallets.find((w) => w.id !== wallets[0].id);
      if (other) setTargetId(other.id);
    }
  }, [wallets, sourceId, targetId]);

  const source = wallets.find((w) => w.id === sourceId);
  const target = wallets.find((w) => w.id === targetId);

  async function getQuote() {
    if (!accessToken || !source || !target) return;
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const newQuote = await apiRequest<FXQuote>("/fx/quote", {
        method: "POST",
        token: accessToken,
        body: { source_currency: source.currency, target_currency: target.currency, source_amount: amount },
      });
      setQuote(newQuote);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not get a quote");
    } finally {
      setBusy(false);
    }
  }

  async function acceptQuote() {
    if (!accessToken || !source || !target || !quote) return;
    setError(null);
    setBusy(true);
    try {
      await apiRequest("/transactions/transfer", {
        method: "POST",
        token: accessToken,
        body: {
          source_wallet_id: source.id,
          destination_wallet_id: target.id,
          amount: quote.source_amount,
          fx_quote_id: quote.id,
          description: `FX conversion ${source.currency} -> ${target.currency}`,
        },
      });
      setResult(`Converted ${quote.source_amount} ${source.currency} to ${quote.target_amount} ${target.currency}.`);
      setQuote(null);
      loadWallets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Conversion failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <table>
          <thead>
            <tr>
              <th>Currency</th>
              <th>Available</th>
              <th>Reserved</th>
              <th>Status</th>
              <th></th>
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
                <td>
                  {!wallet.is_main && wallet.status === "ACTIVE" && (
                    <button onClick={() => setMainWallet(wallet.id)} disabled={settingMainId === wallet.id}>
                      Set as main
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {wallets.length === 0 && (
              <tr>
                <td colSpan={5}>No wallets yet.</td>
              </tr>
            )}
          </tbody>
        </table>
        {error && <p role="alert">{error}</p>}
      </div>

      {wallets.length >= 2 && (
        <div className="tile" style={{ maxWidth: 420 }}>
          <div className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            Convert between your wallets
          </div>
          <label>
            From
            <select value={sourceId} onChange={(e) => { setSourceId(e.target.value); setQuote(null); }}>
              {wallets.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.currency} · {w.available_balance}
                </option>
              ))}
            </select>
          </label>
          <label>
            To
            <select value={targetId} onChange={(e) => { setTargetId(e.target.value); setQuote(null); }}>
              {wallets
                .filter((w) => w.id !== sourceId)
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.currency}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Amount ({source?.currency})
            <input value={amount} onChange={(e) => { setAmount(e.target.value); setQuote(null); }} />
          </label>
          <button onClick={getQuote} disabled={busy || !source || !target}>
            Get quote
          </button>

          {error && <p role="alert">{error}</p>}
          {result && <p>{result}</p>}

          {quote && (
            <div className="tile" style={{ boxShadow: "inset 0 0 0 1px var(--color-accent)" }}>
              <div className="eyebrow">Quote expires {new Date(quote.expires_at).toLocaleTimeString()}</div>
              <table>
                <tbody>
                  <tr>
                    <td>Rate</td>
                    <td style={{ textAlign: "right" }}>
                      1 {quote.source_currency} = {quote.exchange_rate} {quote.target_currency}
                    </td>
                  </tr>
                  <tr>
                    <td>Fee</td>
                    <td style={{ textAlign: "right" }}>
                      {quote.fee} {quote.source_currency}
                    </td>
                  </tr>
                  <tr>
                    <td>You receive</td>
                    <td style={{ textAlign: "right" }}>
                      {quote.target_amount} {quote.target_currency}
                    </td>
                  </tr>
                </tbody>
              </table>
              <button onClick={acceptQuote} disabled={busy}>
                Accept quote
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

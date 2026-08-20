import { ArrowLeftRight, Star } from "lucide-react";
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { FXMarketRate, FXQuote, Wallet } from "../types";

function hueFromString(value: string): number {
  return Math.abs([...value].reduce((sum, ch) => sum + ch.charCodeAt(0), 0)) % 360;
}

function colorForCurrency(currency: string): string {
  return `hsl(${hueFromString(currency)} 65% 55%)`;
}

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
  const [rates, setRates] = useState<Record<string, FXMarketRate>>({});

  function loadWallets() {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
  }

  useEffect(loadWallets, [accessToken]);

  useEffect(() => {
    if (!accessToken || wallets.length < 2) return;
    const mainWallet = wallets.find((w) => w.is_main);
    if (!mainWallet) return;
    const others = wallets.filter((w) => w.currency !== mainWallet.currency);
    Promise.all(
      others.map((w) =>
        apiRequest<FXMarketRate>(
          `/fx/rate?source_currency=${w.currency}&target_currency=${mainWallet.currency}`,
          { token: accessToken },
        ).catch(() => null),
      ),
    ).then((results) => {
      const next: Record<string, FXMarketRate> = {};
      for (const r of results) if (r) next[r.source_currency] = r;
      setRates(next);
    });
  }, [accessToken, wallets]);

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
    <div className="aurora-col">
      <div className="aurora-card">
        <div className="aurora-section-header">
          <div>
            <div className="aurora-eyebrow">Your accounts</div>
            <h2>Wallets</h2>
          </div>
        </div>

        <div className="aurora-wallet-grid">
          {wallets.map((wallet) => (
            <div
              className="aurora-wallet-card"
              key={wallet.id}
              style={{ "--wallet-accent": colorForCurrency(wallet.currency) } as CSSProperties}
            >
              <div className="aurora-wallet-card__top">
                <span className="aurora-wallet-card__code">{wallet.currency}</span>
                {wallet.is_main ? (
                  <span className="aurora-chip aurora-chip-violet">Main</span>
                ) : (
                  <span className="aurora-chip aurora-chip-neutral">{wallet.status}</span>
                )}
              </div>
              <div className="aurora-wallet-card__amount">{wallet.available_balance}</div>
              <div className="aurora-wallet-card__sub">
                {wallet.reserved_balance !== "0" && wallet.reserved_balance !== "0.00"
                  ? `${wallet.reserved_balance} ${wallet.currency} reserved`
                  : "Nothing on hold"}
              </div>
              {!wallet.is_main && rates[wallet.currency] && (
                <div className="aurora-wallet-card__rate">
                  1 {wallet.currency} ≈ {rates[wallet.currency].rate} {rates[wallet.currency].target_currency}
                </div>
              )}
              <div className="aurora-wallet-card__footer">
                <span className="aurora-eyebrow" style={{ marginBottom: 0 }}>
                  {wallet.is_main ? "Main wallet" : wallet.status}
                </span>
                {!wallet.is_main && wallet.status === "ACTIVE" && (
                  <button
                    type="button"
                    className="aurora-wallet-card__set-main"
                    onClick={() => setMainWallet(wallet.id)}
                    disabled={settingMainId === wallet.id}
                  >
                    <Star size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                    Set as main
                  </button>
                )}
              </div>
            </div>
          ))}
          {wallets.length === 0 && <p className="aurora-tx-meta">No wallets yet.</p>}
        </div>
        {error && <p role="alert">{error}</p>}
      </div>

      {wallets.length >= 2 && (
        <div className="aurora-card" style={{ maxWidth: 480 }}>
          <div className="aurora-section-header">
            <div>
              <div className="aurora-eyebrow">Exchange</div>
              <h2>
                <ArrowLeftRight size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
                Convert between your wallets
              </h2>
            </div>
          </div>

          <div className="aurora-convert-grid">
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
          </div>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 12, fontSize: 12.5, fontWeight: 600 }}>
            Amount ({source?.currency})
            <input value={amount} onChange={(e) => { setAmount(e.target.value); setQuote(null); }} />
          </label>
          <button onClick={getQuote} disabled={busy || !source || !target} style={{ marginTop: 14 }}>
            Get quote
          </button>

          {error && <p role="alert">{error}</p>}
          {result && <p>{result}</p>}

          {quote && (
            <div className="aurora-quote-card">
              <div className="aurora-eyebrow">Quote expires {new Date(quote.expires_at).toLocaleTimeString()}</div>
              <div className="aurora-quote-row">
                <span>Rate</span>
                <span>
                  1 {quote.source_currency} = {quote.exchange_rate} {quote.target_currency}
                </span>
              </div>
              <div className="aurora-quote-row">
                <span>Fee</span>
                <span>
                  {quote.fee} {quote.source_currency}
                </span>
              </div>
              <div className="aurora-quote-row total">
                <span>You receive</span>
                <span>
                  {quote.target_amount} {quote.target_currency}
                </span>
              </div>
              <button onClick={acceptQuote} disabled={busy} style={{ marginTop: 10, width: "100%" }}>
                Accept quote
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

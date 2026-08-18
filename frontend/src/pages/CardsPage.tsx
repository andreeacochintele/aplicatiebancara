import { useEffect, useMemo, useState } from "react";

import { ApiError, apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Card, CardType, Wallet } from "../types";

const CARD_TYPES: CardType[] = ["DEBIT", "CREDIT", "ONE_TIME"];

function formatCardType(type: CardType): string {
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function statusClass(status: Card["status"]): string {
  if (status === "ACTIVE") return "tag tag--accent";
  if (status === "FROZEN") return "tag tag--warning";
  return "tag tag--neutral";
}

export function CardsPage() {
  const { accessToken } = useAuth();
  const [cards, setCards] = useState<Card[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selectedType, setSelectedType] = useState<CardType>("DEBIT");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [actionCardId, setActionCardId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeWallets = useMemo(() => wallets.filter((wallet) => wallet.status === "ACTIVE"), [wallets]);

  async function loadCardsData(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const [cardsResponse, walletsResponse] = await Promise.all([
        apiRequest<Card[]>("/cards", { token }),
        apiRequest<Wallet[]>("/wallets", { token }),
      ]);
      setCards(cardsResponse);
      setWallets(walletsResponse);
      const mainWallet = walletsResponse.find((wallet) => wallet.is_main && wallet.status === "ACTIVE");
      setSelectedWalletId((current) => current || mainWallet?.id || "");
    } catch (err) {
      setCards([]);
      setWallets([]);
      setError(err instanceof ApiError ? err.message : "Could not load cards.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken) return;
    void loadCardsData(accessToken);
  }, [accessToken]);

  async function createCard() {
    if (!accessToken || isSaving) return;
    setIsSaving(true);
    setError(null);
    try {
      const card = await apiRequest<Card>("/cards", {
        method: "POST",
        token: accessToken,
        body: {
          type: selectedType,
          default_wallet_id: selectedWalletId || null,
        },
      });
      setCards((current) => [card, ...current]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create card.");
    } finally {
      setIsSaving(false);
    }
  }

  async function updateCardStatus(card: Card) {
    if (!accessToken || actionCardId) return;
    const path = card.status === "FROZEN" ? `/cards/${card.id}/unfreeze` : `/cards/${card.id}/freeze`;
    setActionCardId(card.id);
    setError(null);
    try {
      const updated = await apiRequest<Card>(path, {
        method: "PATCH",
        token: accessToken,
      });
      setCards((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update card.");
    } finally {
      setActionCardId(null);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Card controls</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: "0.75rem" }}>
          <label>
            Card type
            <select value={selectedType} onChange={(event) => setSelectedType(event.target.value as CardType)}>
              {CARD_TYPES.map((type) => (
                <option key={type} value={type}>
                  {formatCardType(type)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Default wallet
            <select value={selectedWalletId} onChange={(event) => setSelectedWalletId(event.target.value)}>
              <option value="">No default wallet</option>
              {activeWallets.map((wallet) => (
                <option key={wallet.id} value={wallet.id}>
                  {wallet.currency}
                  {wallet.is_main ? " - Main" : ""}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={createCard} disabled={isSaving} style={{ alignSelf: "end" }}>
            {isSaving ? "Creating..." : "Create card"}
          </button>
        </div>
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">My cards</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Card</th>
              <th>Type</th>
              <th>Default wallet</th>
              <th>Status</th>
              <th>Expires</th>
              <th style={{ textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {cards.map((card) => {
              const wallet = wallets.find((item) => item.id === card.default_wallet_id);
              return (
                <tr key={card.id}>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>{card.masked_pan}</td>
                  <td>{formatCardType(card.type)}</td>
                  <td>{wallet ? wallet.currency : "None"}</td>
                  <td>
                    <span className={statusClass(card.status)}>{card.status}</span>
                  </td>
                  <td>
                    {String(card.expiration_month).padStart(2, "0")}/{card.expiration_year}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <button
                      type="button"
                      onClick={() => updateCardStatus(card)}
                      disabled={actionCardId === card.id || (card.status !== "ACTIVE" && card.status !== "FROZEN")}
                    >
                      {card.status === "FROZEN" ? "Unfreeze" : "Freeze"}
                    </button>
                  </td>
                </tr>
              );
            })}
            {!isLoading && cards.length === 0 && (
              <tr>
                <td colSpan={6}>No cards yet.</td>
              </tr>
            )}
            {isLoading && (
              <tr>
                <td colSpan={6}>Loading cards...</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

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

function cardToneClass(type: CardType): string {
  if (type === "CREDIT") return "bank-card bank-card--credit";
  if (type === "ONE_TIME") return "bank-card bank-card--one-time";
  return "bank-card bank-card--debit";
}

export function CardsPage() {
  const { accessToken, logout, user } = useAuth();
  const [cards, setCards] = useState<Card[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selectedType, setSelectedType] = useState<CardType>("DEBIT");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [actionCardId, setActionCardId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeWallets = useMemo(() => wallets.filter((wallet) => wallet.status === "ACTIVE"), [wallets]);
  const cardholderName = user ? `${user.first_name} ${user.last_name}`.trim() : "Card holder";

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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
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
  }, [accessToken, logout]);

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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
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
        {isLoading && <div className="card-empty">Loading cards...</div>}
        {!isLoading && cards.length === 0 && <div className="card-empty">No cards yet.</div>}
        {!isLoading && cards.length > 0 && (
          <div className="card-gallery">
            {cards.map((card) => {
              const wallet = wallets.find((item) => item.id === card.default_wallet_id);
              return (
                <article className="card-panel" key={card.id}>
                  <div className={cardToneClass(card.type)}>
                    <div className="bank-card__top">
                      <span className="bank-card__brand">BANKING</span>
                      <span className={statusClass(card.status)}>{card.status}</span>
                    </div>
                    <div className="bank-card__chip" aria-hidden="true" />
                    <div className="bank-card__number">{card.masked_pan}</div>
                    <div className="bank-card__holder">
                      <span>Card holder</span>
                      <strong>{cardholderName}</strong>
                    </div>
                    <div className="bank-card__footer">
                      <span>{formatCardType(card.type)}</span>
                      <span>
                        {String(card.expiration_month).padStart(2, "0")}/{card.expiration_year}
                      </span>
                    </div>
                  </div>

                  <div className="card-panel__meta">
                    <div>
                      <div className="eyebrow">Default wallet</div>
                      <div className="card-panel__value">{wallet ? wallet.currency : "None"}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => updateCardStatus(card)}
                      disabled={actionCardId === card.id || (card.status !== "ACTIVE" && card.status !== "FROZEN")}
                    >
                      {card.status === "FROZEN" ? "Unfreeze" : "Freeze"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { ApiError, apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { CreditProfile, CreditScore } from "../types";

function bandClass(band: string): string {
  if (band === "EXCELLENT" || band === "VERY_GOOD" || band === "GOOD") return "tag tag--accent";
  if (band === "FAIR") return "tag tag--neutral";
  return "tag tag--warning";
}

function formatFactorLabel(key: string): string {
  return key
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

export function CreditPage() {
  const { accessToken, logout } = useAuth();
  const [profile, setProfile] = useState<CreditProfile | null>(null);
  const [score, setScore] = useState<CreditScore | null>(null);
  const [income, setIncome] = useState("");
  const [existingDebt, setExistingDebt] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scorePercent = useMemo(() => {
    if (!score) return 0;
    return Math.round(((score.score - 300) / 550) * 100);
  }, [score]);

  async function loadCreditData(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const [profileResponse, scoreResponse] = await Promise.all([
        apiRequest<CreditProfile>("/credit/profile", { token }),
        apiRequest<CreditScore>("/credit/score", { token }),
      ]);
      setProfile(profileResponse);
      setScore(scoreResponse);
      setIncome(profileResponse.income);
      setExistingDebt(profileResponse.existing_debt);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not load credit score.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken) return;
    void loadCreditData(accessToken);
  }, [accessToken, logout]);

  async function recalculateScore() {
    if (!accessToken || isSaving) return;
    setIsSaving(true);
    setError(null);
    try {
      const scoreResponse = await apiRequest<CreditScore>("/credit/score/recalculate", {
        method: "POST",
        token: accessToken,
        body: {
          income: income || null,
          existing_debt: existingDebt || null,
        },
      });
      const profileResponse = await apiRequest<CreditProfile>("/credit/profile", { token: accessToken });
      setScore(scoreResponse);
      setProfile(profileResponse);
      setIncome(profileResponse.income);
      setExistingDebt(profileResponse.existing_debt);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not recalculate score.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Credit score</span>
          {score && <span className={bandClass(score.band)}>{score.band}</span>}
        </div>

        {isLoading && <div className="card-empty">Loading credit score...</div>}
        {!isLoading && score && (
          <div className="credit-score-layout">
            <div>
              <div className="credit-score-ring" style={{ "--score-percent": `${scorePercent}%` } as CSSProperties}>
                <div>
                  <span>{score.score}</span>
                  <small>/ 850</small>
                </div>
              </div>
            </div>
            <div className="credit-factor-grid">
              {Object.entries(score.reason_data).map(([key, value]) => (
                <div className="credit-factor" key={key}>
                  <div className="eyebrow">{formatFactorLabel(key)}</div>
                  <div className="card-panel__value">{value}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Mock profile inputs</span>
        </div>
        <div className="credit-form-grid">
          <label>
            Monthly income
            <input value={income} onChange={(event) => setIncome(event.target.value)} inputMode="decimal" />
          </label>
          <label>
            Existing debt
            <input value={existingDebt} onChange={(event) => setExistingDebt(event.target.value)} inputMode="decimal" />
          </label>
          <button type="button" onClick={recalculateScore} disabled={isSaving}>
            {isSaving ? "Recalculating..." : "Recalculate score"}
          </button>
        </div>
        {profile && (
          <div className="credit-profile-meta">
            <span>Last updated</span>
            <strong>{new Date(profile.updated_at).toLocaleString()}</strong>
          </div>
        )}
      </div>
    </section>
  );
}

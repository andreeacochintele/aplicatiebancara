import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { apiRequest } from "../api/apiClient";
import type { User } from "../types";

const IDLE_TIMEOUT_MS = 15 * 60 * 1000;
const IDLE_WARNING_MS = 30 * 1000;
const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "scroll", "touchstart"] as const;

interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  idleWarningSeconds: number | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const STORAGE_KEY = "banking_app_auth";

interface StoredAuth {
  user: User;
  tokens: AuthTokens;
}

function loadStoredAuth(): StoredAuth | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredAuth;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [stored, setStored] = useState<StoredAuth | null>(loadStoredAuth);
  const [idleWarningSeconds, setIdleWarningSeconds] = useState<number | null>(null);

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiRequest<{ user: User; tokens: AuthTokens }>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(response));
    setStored(response);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setStored(null);
    setIdleWarningSeconds(null);
  }, []);

  const logoutTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warningTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!stored) return;

    function clearTimers() {
      if (logoutTimer.current) clearTimeout(logoutTimer.current);
      if (warningTimer.current) clearTimeout(warningTimer.current);
      if (countdownInterval.current) clearInterval(countdownInterval.current);
    }

    function startWarningCountdown() {
      let remaining = Math.round(IDLE_WARNING_MS / 1000);
      setIdleWarningSeconds(remaining);
      countdownInterval.current = setInterval(() => {
        remaining -= 1;
        setIdleWarningSeconds(Math.max(remaining, 0));
      }, 1000);
    }

    function resetIdleTimer() {
      clearTimers();
      setIdleWarningSeconds(null);
      warningTimer.current = setTimeout(startWarningCountdown, IDLE_TIMEOUT_MS - IDLE_WARNING_MS);
      logoutTimer.current = setTimeout(logout, IDLE_TIMEOUT_MS);
    }

    resetIdleTimer();
    for (const event of ACTIVITY_EVENTS) window.addEventListener(event, resetIdleTimer);

    return () => {
      clearTimers();
      for (const event of ACTIVITY_EVENTS) window.removeEventListener(event, resetIdleTimer);
    };
  }, [stored, logout]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: stored?.user ?? null,
      accessToken: stored?.tokens.access_token ?? null,
      isAuthenticated: stored !== null,
      idleWarningSeconds,
      login,
      logout,
    }),
    [stored, idleWarningSeconds, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { getMyFullProfile, loginUser, registerUser, type AuthResponse, type AuthTokens } from "../features/auth";
import type { RegisterPayload, User } from "../types";

const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
const IDLE_WARNING_MS = 30 * 1000;
const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "scroll", "touchstart"] as const;

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  idleWarningSeconds: number | null;
  onboardingCompleted: boolean | null;
  login: (email: string, password: string) => Promise<AuthResponse>;
  register: (payload: RegisterPayload) => Promise<AuthResponse>;
  logout: () => void;
  markOnboardingCompleted: () => void;
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
  const [onboardingCompleted, setOnboardingCompleted] = useState<boolean | null>(null);

  const storeAuth = useCallback((response: StoredAuth) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(response));
    setStored(response);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await loginUser(email, password);
    storeAuth(response);
    return response;
  }, [storeAuth]);

  const register = useCallback(
    async (payload: RegisterPayload) => {
      const response = await registerUser(payload);
      storeAuth(response);
      return response;
    },
    [storeAuth],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setStored(null);
    setIdleWarningSeconds(null);
  }, []);

  const markOnboardingCompleted = useCallback(() => {
    setOnboardingCompleted(true);
  }, []);

  const accessToken = stored?.tokens.access_token ?? null;

  useEffect(() => {
    if (!accessToken) {
      setOnboardingCompleted(null);
      return;
    }
    let cancelled = false;
    getMyFullProfile(accessToken)
      .then((profile) => {
        if (!cancelled) setOnboardingCompleted(profile.onboarding.completed);
      })
      .catch(() => {
        if (!cancelled) setOnboardingCompleted(null);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

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
      accessToken,
      isAuthenticated: stored !== null,
      idleWarningSeconds,
      onboardingCompleted,
      login,
      register,
      logout,
      markOnboardingCompleted,
    }),
    [stored, accessToken, idleWarningSeconds, onboardingCompleted, login, register, logout, markOnboardingCompleted],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

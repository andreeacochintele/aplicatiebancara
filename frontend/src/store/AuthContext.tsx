import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { getMyFullProfile, loginUser, registerUser, type AuthResponse, type AuthTokens } from "../features/auth";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  onboardingCompleted: boolean | null;
  login: (email: string, password: string) => Promise<AuthResponse>;
  register: (payload: {
    first_name: string;
    last_name: string;
    email: string;
    phone: string;
    password: string;
  }) => Promise<AuthResponse>;
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
    async (payload: {
      first_name: string;
      last_name: string;
      email: string;
      phone: string;
      password: string;
    }) => {
      const response = await registerUser(payload);
      storeAuth(response);
      return response;
    },
    [storeAuth],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setStored(null);
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

  const value = useMemo<AuthContextValue>(
    () => ({
      user: stored?.user ?? null,
      accessToken,
      isAuthenticated: stored !== null,
      onboardingCompleted,
      login,
      register,
      logout,
      markOnboardingCompleted,
    }),
    [stored, accessToken, onboardingCompleted, login, register, logout, markOnboardingCompleted],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

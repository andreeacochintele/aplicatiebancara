import { createContext, useCallback, useMemo, useState, type ReactNode } from "react";

import { loginUser, registerUser, type AuthResponse, type AuthTokens } from "../features/auth";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<AuthResponse>;
  register: (payload: {
    first_name: string;
    last_name: string;
    email: string;
    phone: string;
    password: string;
  }) => Promise<AuthResponse>;
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

  const value = useMemo<AuthContextValue>(
    () => ({
      user: stored?.user ?? null,
      accessToken: stored?.tokens.access_token ?? null,
      isAuthenticated: stored !== null,
      login,
      register,
      logout,
    }),
    [stored, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

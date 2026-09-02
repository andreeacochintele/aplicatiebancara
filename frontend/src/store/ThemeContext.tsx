import { createContext, useCallback, useEffect, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "banking_app_theme";
const HIVE_STORAGE_KEY = "banking_app_hive_mode";

interface ThemeContextValue {
  theme: Theme;
  hiveMode: boolean;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  toggleHiveMode: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function loadStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "dark";
}

function loadStoredHiveMode(): boolean {
  return localStorage.getItem(HIVE_STORAGE_KEY) === "on";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(loadStoredTheme);
  const [hiveMode, setHiveMode] = useState<boolean>(loadStoredHiveMode);

  useEffect(() => {
    // index.html sets this synchronously pre-paint to avoid a flash; this
    // keeps it in sync whenever the user actually changes the theme.
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.hiveMode = hiveMode ? "on" : "off";
    localStorage.setItem(HIVE_STORAGE_KEY, hiveMode ? "on" : "off");
  }, [hiveMode]);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);
  const toggleTheme = useCallback(() => setThemeState((current) => (current === "dark" ? "light" : "dark")), []);
  const toggleHiveMode = useCallback(() => setHiveMode((current) => !current), []);

  return <ThemeContext.Provider value={{ theme, hiveMode, setTheme, toggleTheme, toggleHiveMode }}>{children}</ThemeContext.Provider>;
}

import { Moon, Sun } from "lucide-react";

import { useTheme } from "../hooks/useTheme";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      onClick={toggleTheme}
      className="theme-toggle"
    >
      {theme === "dark" ? <Sun size={22} strokeWidth={2.25} /> : <Moon size={22} strokeWidth={2.25} />}
    </button>
  );
}

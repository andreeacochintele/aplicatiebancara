import { Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useTheme } from "../hooks/useTheme";

export function ThemeToggle() {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      aria-label={theme === "dark" ? t("common.switchToLight") : t("common.switchToDark")}
      title={theme === "dark" ? t("common.switchToLight") : t("common.switchToDark")}
      onClick={toggleTheme}
      className="theme-toggle"
    >
      {theme === "dark" ? <Sun size={22} strokeWidth={2.25} /> : <Moon size={22} strokeWidth={2.25} />}
    </button>
  );
}

import { useTranslation } from "react-i18next";

import { useTheme } from "../hooks/useTheme";

export function HiveModeToggle() {
  const { t } = useTranslation();
  const { hiveMode, toggleHiveMode } = useTheme();

  return (
    <button
      type="button"
      aria-pressed={hiveMode}
      aria-label={hiveMode ? t("common.disableHiveMode") : t("common.enableHiveMode")}
      title={hiveMode ? t("common.disableHiveMode") : t("common.enableHiveMode")}
      onClick={toggleHiveMode}
      className={`theme-toggle hive-mode-toggle${hiveMode ? " hive-mode-toggle--active" : ""}`}
    >
      <svg className="hive-mode-toggle__hive" viewBox="0 0 24 24" aria-hidden="true">
        <path className="hive-mode-toggle__body" d="M12 3.5c4.2 0 7.6 3.8 7.6 8.9v4.1c0 2.2-1.7 4-3.8 4H8.2c-2.1 0-3.8-1.8-3.8-4v-4.1c0-5.1 3.4-8.9 7.6-8.9Z" />
        <path className="hive-mode-toggle__line" d="M6.4 10.2h11.2" />
        <path className="hive-mode-toggle__line" d="M5.2 14.1h13.6" />
        <path className="hive-mode-toggle__door" d="M9.9 19v-1.2c0-1.2.9-2.1 2.1-2.1s2.1.9 2.1 2.1V19" />
      </svg>
    </button>
  );
}

import { useTranslation } from "react-i18next";

import { useAuth } from "../hooks/useAuth";

export function IdleWarning() {
  const { t } = useTranslation();
  const { idleWarningSeconds } = useAuth();
  if (idleWarningSeconds === null) return null;

  return (
    <div
      role="alert"
      style={{
        position: "fixed",
        bottom: 20,
        right: 20,
        zIndex: 1000,
        background: "var(--idle-warning-bg, #1f1330)",
        color: "var(--idle-warning-text, #fff)",
        border: "1px solid var(--idle-warning-border, transparent)",
        padding: "12px 18px",
        borderRadius: 12,
        fontSize: 13,
        fontWeight: 600,
        boxShadow: "0 12px 28px -8px rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: "var(--idle-warning-dot, #ff6fa5)",
          flexShrink: 0,
        }}
      />
      {t("common.idleWarning", { seconds: idleWarningSeconds })}
    </div>
  );
}

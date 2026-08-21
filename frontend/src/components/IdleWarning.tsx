import { useAuth } from "../hooks/useAuth";

export function IdleWarning() {
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
        background: "#1f1330",
        color: "#fff",
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
          background: "#ff6fa5",
          flexShrink: 0,
        }}
      />
      Auto logout in {idleWarningSeconds}s — move your mouse to stay signed in
    </div>
  );
}

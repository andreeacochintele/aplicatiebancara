import { useContext } from "react";

import { PeriodContext } from "../store/PeriodContext";

export function usePeriod() {
  const context = useContext(PeriodContext);
  if (!context) {
    throw new Error("usePeriod must be used within a PeriodProvider");
  }
  return context;
}

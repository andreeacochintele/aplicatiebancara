import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import "./features/auth/flags.css";
import "./i18n/config";
import "./index.css";
import "./styles/easyb.css";
import { AuthProvider } from "./store/AuthContext";
import { PeriodProvider } from "./store/PeriodContext";
import { ThemeProvider } from "./store/ThemeContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <PeriodProvider>
            <App />
          </PeriodProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch: {
      // Bind-mounted volumes under Docker Desktop on Windows don't reliably
      // deliver native filesystem events, so HMR silently misses edits
      // without polling.
      usePolling: true,
    },
  },
});

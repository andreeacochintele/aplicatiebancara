import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Docker Desktop on Windows doesn't propagate native filesystem change
    // events through the bind mount, so Vite's default watcher never fires
    // and keeps serving stale modules. Polling works around that.
    watch: {
      usePolling: true,
    },
  },
});

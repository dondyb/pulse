import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only ever talks to this server; /api is proxied to the backend,
// so Docker service names never appear in browser-facing requests.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    host: "0.0.0.0",
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
    watch: { usePolling: process.env.CHOKIDAR_USEPOLLING === "true" },
  },
  preview: { port: 3000 },
});

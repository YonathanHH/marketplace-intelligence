import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs as a separate FastAPI process in development; Vite proxies
// /api to it so the frontend can use same-origin relative URLs in both dev
// and production (where FastAPI serves the built bundle itself).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
});

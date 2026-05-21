import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Local dev: Vite serves the UI on :5173; proxy /api to FastAPI (uvicorn glass_ui_api:app, default :8000).
// Set VITE_GLASS_API_PROXY in .env.local if your API runs elsewhere (e.g. http://127.0.0.1:8080).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_GLASS_API_PROXY || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      host: "0.0.0.0",
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
    },
  };
});


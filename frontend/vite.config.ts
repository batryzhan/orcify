import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api жергілікті FastAPI-ға проксиленеді: EventSource same-origin жұмыс істейді.
// ORCIFY_API_URL — бэкенд 8000 портта емес іске қосылса.
// (process globalThis арқылы оқылады, бір айнымалы үшін @types/node тартпау үшін.)
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const apiTarget = env.ORCIFY_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
});

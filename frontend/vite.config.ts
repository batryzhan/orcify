import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api проксируется на локальный FastAPI: EventSource работает same-origin.
// ORCIFY_API_URL — если бэкенд запущен не на 8000.
// (process читается через globalThis, чтобы не тянуть @types/node ради одной переменной.)
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const apiTarget = env.ORCIFY_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
});

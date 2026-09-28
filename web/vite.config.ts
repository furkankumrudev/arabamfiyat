import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the dev server forwards /api to the local API, so the browser
// talks to one origin: no CORS, and API errors reach the page with their real
// message instead of an opaque "Failed to fetch".
const apiTarget = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { "/api": apiTarget, "/docs": apiTarget, "/openapi.json": apiTarget } },
});

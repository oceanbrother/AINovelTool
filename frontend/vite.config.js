import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend routes have no common prefix, so proxy each top-level API path.
const backend = "http://127.0.0.1:8000";
const apiPaths = ["/projects", "/idioms", "/literary", "/health"];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      apiPaths.map((p) => [p, { target: backend, changeOrigin: true }])
    ),
  },
});

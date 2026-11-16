/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// ADR-002: a static single-page app. In development `/api` is proxied to the local API,
// so the browser only ever talks to one origin (the same shape as hosting, ADR-007).
export default defineConfig({
  // The public demo lives under a sub-path (D-79); the app itself is served from the root.
  base: process.env.VITE_BASE ?? "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Test output is not part of the app: watching it reloads the page during a test run.
    watch: { ignored: ["**/coverage/**", "**/playwright-report/**", "**/test-results/**"] },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    globals: true,
    setupFiles: ["tests/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/features/**"],
      // Handbook section 9: 70% on features/.
      thresholds: { lines: 70, branches: 70, functions: 70, statements: 70 },
    },
  },
});

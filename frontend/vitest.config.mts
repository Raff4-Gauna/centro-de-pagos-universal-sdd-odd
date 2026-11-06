import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Components run in jsdom; server-side files (route handlers, lib/server) opt into the node
// environment with a `// @vitest-environment node` docblock. The json-summary
// report is gated by the `frontend` entry of scripts/coverage_thresholds.toml (AC-PLT-22).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // scripts/: build-time checks run by frontend/Dockerfile (check-client-bundle.ts, AC-PLT-29).
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.ts"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reportsDirectory: "coverage",
      reporter: ["text", "json-summary"],
      include: ["src/**/*.{ts,tsx}", "scripts/**/*.ts"],
      exclude: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.ts", "src/types/**"],
    },
  },
});

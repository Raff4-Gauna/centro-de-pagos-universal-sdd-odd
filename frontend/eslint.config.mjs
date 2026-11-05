// ESLint 9 flat config (RN-PLT-11, step 1). CI runs `eslint . --max-warnings 0`: a warning fails too.
// Formatting is prettier's job (`pnpm format:check`); eslint-config-next carries no style rules.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  // Build output, coverage reports and generated declarations are not source: next-env.d.ts
  // (Next) and src/types/** (`pnpm openapi:types` from the OpenAPI contract, ADR-0005).
  globalIgnores([".next/**", "out/**", "coverage/**", "next-env.d.ts", "src/types/**"]),
]);

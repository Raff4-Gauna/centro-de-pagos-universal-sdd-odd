// Adds the jest-dom matchers (toBeInTheDocument, ...) to vitest's `expect`, types included.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only unmounts by itself when the runner exposes a global `afterEach` (vitest
// `globals: true`, off here): without this, a component rendered by one test leaks into the next.
afterEach(() => {
  cleanup();
});

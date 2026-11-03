// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { parseRequestId, resolveRequestId } from "./request-id";

// `server-only` throws outside the react-server condition; the guard itself is checked in
// backend-proxy.test.ts (test_RN_PLT_16_backend_url_read_at_runtime_server_only).
vi.mock("server-only", () => ({}));

const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const VALID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";

describe("X-Request-ID in the BFF (AC-PLT-09, RN-PLT-07)", () => {
  it("test_AC_PLT_09_bff_keeps_valid_uuid4", () => {
    expect(parseRequestId(VALID)).toBe(VALID);
    expect(resolveRequestId(VALID)).toBe(VALID);
    // The match is case-insensitive and the accepted value is kept as it arrived.
    const upper = VALID.toUpperCase();
    expect(parseRequestId(upper)).toBe(upper);
    expect(resolveRequestId(upper)).toBe(upper);
  });

  it("test_AC_PLT_09_bff_replaces_invalid_or_newline", () => {
    const invalid: (string | null | undefined)[] = [
      null,
      undefined,
      "",
      "not-a-uuid",
      `${VALID}\n`, // a trailing newline must not pass (full match, not `$`-before-newline)
      `\n${VALID}`,
      `${VALID.slice(0, 35)}\n`, // 36 chars, last one is a newline
      `${VALID}\r\nx-injected: 1`,
      "3f2b8c1e-9d4a-1b7e-8f61-2a5c9e0d7b13", // version 1, not 4
      "3f2b8c1e-9d4a-4b7e-7f61-2a5c9e0d7b13", // wrong variant nibble
      `{${VALID}}`,
      VALID.replaceAll("-", ""),
      "x".repeat(10 * 1024),
    ];

    for (const value of invalid) {
      expect(parseRequestId(value)).toBeNull();
      const replaced = resolveRequestId(value);
      expect(replaced).toMatch(UUID4);
      expect(replaced).not.toBe(value);
    }
    // Every replacement is a fresh UUIDv4.
    expect(resolveRequestId("bad")).not.toBe(resolveRequestId("bad"));
  });
});

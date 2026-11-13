// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  DEFAULT_RETURN_PATH,
  MAX_RETURN_PATH_LENGTH,
  returnUrl,
  sanitizeReturnPath,
} from "./return-path";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const APP = "https://app.example";

// The rule of `sanitize_return_path` (backend/apps/identity/domain/return_path.py): both agree.
const HOSTILE: unknown[] = [
  "https://evil.example/x",
  "http://evil.example",
  "javascript:alert(1)",
  "data:text/html,x",
  "//evil.example",
  "//evil.example/path",
  "///evil.example",
  "/\\evil.example",
  "\\\\evil.example",
  "\\/evil.example",
  "/\t/evil.example",
  "/\n/evil.example",
  "/\r/evil.example",
  "/ok\u0000",
  "/\u0000/evil.example",
  "/a\u007fb",
  "/a​b", // zero-width space (Cf): invisible, dropped by some parsers
  "/a b", // no-break space (Zs)
  "/a b", // line separator (Zl)
  "/a\ud800b", // lone surrogate (Cs)
  "evil.example",
  "%2F%2Fevil.example", // encoded, without the leading slash: not a path
  "",
  "/" + "a".repeat(MAX_RETURN_PATH_LENGTH),
  null,
  undefined,
  42,
  { path: "/x" },
  ["/x"],
];

const INTERNAL = [
  "/",
  "/cobros",
  "/cobros/123?tab=detalle#linea",
  "/configuracion/perfil",
  "/buscar?q=a b", // the ASCII space is printable, as in Python
  "/" + "a".repeat(MAX_RETURN_PATH_LENGTH - 1),
  "/" + "😀".repeat(MAX_RETURN_PATH_LENGTH - 1), // 511 code points, 1022 UTF-16 units
];

describe("return path in the BFF (AC-IDA-19, RN-IDA-13)", () => {
  it("test_AC_IDA_19_hostile_return_path_becomes_home", () => {
    for (const value of HOSTILE) {
      expect(sanitizeReturnPath(value), JSON.stringify(value)).toBe(DEFAULT_RETURN_PATH);
      expect(returnUrl(value, APP).href, JSON.stringify(value)).toBe(`${APP}/`);
    }
  });

  it("test_AC_IDA_19_internal_path_is_kept_whole", () => {
    for (const value of INTERNAL) {
      expect(sanitizeReturnPath(value)).toBe(value);
      expect(returnUrl(value, APP).origin).toBe(APP);
    }
    expect(returnUrl("/cobros/123?tab=detalle", APP).href).toBe(`${APP}/cobros/123?tab=detalle`);
  });

  it("test_AC_IDA_19_encoded_path_is_not_decoded_before_the_check", () => {
    // Checked as sent: no decoding round turns them into `//host` or `/\host`. A browser does not
    // decode a redirect target either, so each one stays a path of the app.
    for (const value of [
      "/%2F%2Fevil.example",
      "/%2f%2fevil.example",
      "/%5Cevil.example",
      "/%5c%5cevil.example",
      "/%252F%252Fevil.example",
      "/%09/evil.example",
      "/%00",
    ]) {
      expect(sanitizeReturnPath(value)).toBe(value);
      const target = returnUrl(value, APP);
      expect(target.origin).toBe(APP);
      expect(target.pathname).toBe(value);
    }
  });

  it("test_AC_IDA_19_unicode_lookalike_slash_stays_on_the_app", () => {
    // U+FF0F FULLWIDTH SOLIDUS and U+2215 DIVISION SLASH are printable (accepted by Django too),
    // and the URL parser percent-encodes them in a path, never reading them as `/`.
    for (const value of ["/／evil.example", "/∕evil.example", "/＼evil.example"]) {
      expect(sanitizeReturnPath(value)).toBe(value);
      const target = returnUrl(value, APP);
      expect(target.origin).toBe(APP);
      expect(target.pathname.startsWith("/%")).toBe(true);
    }
    // Without the leading ASCII `/` it is not a path at all.
    expect(sanitizeReturnPath("／／evil.example")).toBe(DEFAULT_RETURN_PATH);
  });

  it("test_AC_IDA_19_redirect_never_leaves_the_app_origin", () => {
    expect(returnUrl("/x", `${APP}/ignored/path`).href).toBe(`${APP}/x`);
    expect(returnUrl("//evil.example", "http://localhost:3000").href).toBe(
      "http://localhost:3000/",
    );
  });
});

// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  COOKIE_NAMES,
  type BffCookie,
  accessCookie,
  clearedCookie,
  csrfCookie,
  loginCookie,
  organizationCookie,
  randomCookieToken,
  refreshCookie,
  serializeCookie,
} from "./cookies";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const JWT = "eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl";
const REFRESH = "rt1.3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13.c2VjcmV0LXZhbHVlLWZvci10ZXN0cw";
const TOKEN = "A".repeat(43);
const ORG = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";

// Attributes of a Set-Cookie value, keys in lower case (`name` and `value` for the pair).
function parse(header: string): Record<string, string | true> {
  const [pair, ...attributes] = header.split("; ");
  const [name, value] = pair!.split(/=(.*)/s);
  const parsed: Record<string, string | true> = { name: name!, value: value ?? "" };
  for (const attribute of attributes) {
    const [key, attributeValue] = attribute.split("=");
    parsed[key!.toLowerCase()] = attributeValue ?? true;
  }
  return parsed;
}

function every(): BffCookie[] {
  return [
    accessCookie(JWT, 900),
    refreshCookie(REFRESH, 604_800),
    csrfCookie(TOKEN, 604_800),
    loginCookie(TOKEN),
    organizationCookie(ORG),
    ...Object.values(COOKIE_NAMES).map(clearedCookie),
  ];
}

describe("BFF cookies (AC-IDA-18, RN-IDA-12, design.md §7.1)", () => {
  it("test_AC_IDA_18_every_cookie_is_host_prefixed_secure_and_lax", () => {
    for (const bffCookie of every()) {
      const parsed = parse(serializeCookie(bffCookie));
      expect(parsed.name).toMatch(/^__Host-cpu_/);
      // What the `__Host-` prefix requires, or the browser drops the cookie.
      expect(parsed.secure, parsed.name as string).toBe(true);
      expect(parsed.path).toBe("/");
      expect(parsed).not.toHaveProperty("domain");
      expect(parsed.samesite).toBe("Lax");
      expect(parsed["max-age"]).toMatch(/^\d+$/);
    }
  });

  it("test_AC_IDA_18_tokens_only_travel_in_http_only_cookies", () => {
    for (const bffCookie of [
      accessCookie(JWT, 900),
      refreshCookie(REFRESH, 604_800),
      loginCookie(TOKEN),
      organizationCookie(ORG),
    ]) {
      expect(parse(serializeCookie(bffCookie)).httponly, bffCookie.name).toBe(true);
    }
    // The CSRF token is the one JavaScript reads (double submit); it is no session token.
    const csrf = parse(serializeCookie(csrfCookie(TOKEN, 604_800)));
    expect(csrf.name).toBe("__Host-cpu_csrf");
    expect(csrf).not.toHaveProperty("httponly");
  });

  it("test_AC_IDA_18_lifetimes_follow_the_session", () => {
    // The access cookie dies a minute before the token: the BFF refreshes before Django rejects it.
    expect(accessCookie(JWT, 900).maxAge).toBe(840);
    expect(accessCookie(JWT, 30).maxAge).toBe(0);
    expect(refreshCookie(REFRESH, 604_800).maxAge).toBe(604_800);
    expect(csrfCookie(TOKEN, 604_800).maxAge).toBe(604_800);
    // Never past the absolute life of a session (30 d).
    expect(refreshCookie(REFRESH, 90 * 86_400).maxAge).toBe(30 * 86_400);
    expect(loginCookie(TOKEN).maxAge).toBe(600);
    expect(organizationCookie(ORG).maxAge).toBe(30 * 86_400);
  });

  it("test_AC_IDA_18_cleared_cookie_keeps_the_attributes", () => {
    for (const name of Object.values(COOKIE_NAMES)) {
      const parsed = parse(serializeCookie(clearedCookie(name)));
      expect(parsed).toMatchObject({ name, value: "", "max-age": "0", path: "/", secure: true });
      expect(parsed.httponly === true).toBe(name !== COOKIE_NAMES.csrf);
    }
  });

  it("test_AC_IDA_18_value_cannot_inject_attributes", () => {
    for (const value of ["x; Domain=evil.example", "x\r\nSet-Cookie: a=b", "a b", 'a"b', "ñ"]) {
      expect(() => refreshCookie(value, 60)).toThrow(TypeError);
      expect(() => refreshCookie(value, 60)).not.toThrow(value);
    }
    expect(() =>
      serializeCookie({ ...loginCookie(TOKEN), value: "x;Domain=evil.example" }),
    ).toThrow(TypeError);
    for (const lifetime of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => refreshCookie(REFRESH, lifetime)).toThrow(RangeError);
    }
  });

  it("test_AC_IDA_18_random_token_is_32_bytes_base64url", () => {
    const token = randomCookieToken();
    expect(token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(randomCookieToken()).not.toBe(token);
  });
});

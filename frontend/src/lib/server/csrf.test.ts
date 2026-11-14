// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  checkCsrf,
  checkCsrfToken,
  checkOrigin,
  csrfFailure,
  isSafeMethod,
  requestCookieValues,
} from "./csrf";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const APP_ORIGIN = "https://app.example.test";
const TOKEN = "c".repeat(43);
const REQUEST_ID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";

function request(method: string, headers: Record<string, string>): Request {
  return new Request(`${APP_ORIGIN}/api/session/active-organization`, { method, headers });
}

// A mutation as the api-client sends it: same origin, header and cookie with the same token.
function legitimate(overrides: Record<string, string | null> = {}): Request {
  const headers: Record<string, string> = {
    origin: APP_ORIGIN,
    "x-csrf-token": TOKEN,
    cookie: `__Host-cpu_at=jwt; __Host-cpu_csrf=${TOKEN}`,
  };
  for (const [name, value] of Object.entries(overrides)) {
    if (value === null) {
      delete headers[name];
    } else {
      headers[name] = value;
    }
  }
  return request("POST", headers);
}

beforeEach(() => {
  vi.stubEnv("HUB_APP_ORIGIN", APP_ORIGIN);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("CSRF of the BFF (RN-IDA-13, design.md §7.2)", () => {
  it("test_AC_IDA_19_same_origin_mutation_with_matching_token_passes", () => {
    expect(checkCsrf(legitimate())).toEqual({ ok: true });
  });

  it("test_AC_IDA_19_mutation_without_origin_nor_fetch_site_is_refused", () => {
    expect(checkCsrf(legitimate({ origin: null }))).toEqual({
      ok: false,
      reason: "origin_missing",
    });
  });

  it("test_AC_IDA_19_mutation_without_origin_falls_back_to_sec_fetch_site", () => {
    expect(checkCsrf(legitimate({ origin: null, "sec-fetch-site": "same-origin" }))).toEqual({
      ok: true,
    });
    for (const site of ["same-site", "cross-site", "none"]) {
      expect(checkCsrf(legitimate({ origin: null, "sec-fetch-site": site }))).toEqual({
        ok: false,
        reason: "origin_mismatch",
      });
    }
  });

  it("test_AC_IDA_19_mutation_from_a_foreign_origin_is_refused", () => {
    const foreign = [
      "https://evil.example",
      "https://app.example.test.evil.example",
      "http://app.example.test",
      "https://app.example.test:8443",
      "null",
      `${APP_ORIGIN}/`,
    ];
    for (const origin of foreign) {
      // Origin decides: a same-origin Sec-Fetch-Site next to it does not rescue it.
      const check = checkCsrf(legitimate({ origin, "sec-fetch-site": "same-origin" }));
      expect(check).toEqual({ ok: false, reason: "origin_mismatch" });
    }
  });

  it("test_AC_IDA_19_mutation_with_a_different_token_is_refused", () => {
    expect(checkCsrf(legitimate({ "x-csrf-token": "d".repeat(43) }))).toEqual({
      ok: false,
      reason: "token_mismatch",
    });
    // A prefix of the real token is not a match either.
    expect(checkCsrf(legitimate({ "x-csrf-token": TOKEN.slice(0, 42) }))).toEqual({
      ok: false,
      reason: "token_mismatch",
    });
  });

  it("test_AC_IDA_19_mutation_without_token_or_cookie_is_refused", () => {
    const missing = [
      legitimate({ "x-csrf-token": null }),
      legitimate({ "x-csrf-token": "" }),
      legitimate({ cookie: "__Host-cpu_at=jwt" }),
      legitimate({ cookie: null }),
      legitimate({ cookie: "__Host-cpu_csrf=" }),
      // Two CSRF cookies are ambiguous: neither is picked.
      legitimate({ cookie: `__Host-cpu_csrf=${TOKEN}; __Host-cpu_csrf=${TOKEN}` }),
      // A cookie whose name only ends like the real one does not count.
      legitimate({ cookie: `x__Host-cpu_csrf=${TOKEN}` }),
    ];
    for (const candidate of missing) {
      expect(checkCsrf(candidate)).toEqual({ ok: false, reason: "token_missing" });
    }
  });

  it("test_AC_IDA_19_every_unsafe_method_is_checked", () => {
    for (const method of ["POST", "PUT", "PATCH", "DELETE", "post", "PROPFIND"]) {
      const forged = request(method, { origin: "https://evil.example" });
      expect(checkCsrf(forged)).toEqual({ ok: false, reason: "origin_mismatch" });
    }
  });

  it("test_AC_IDA_19_safe_methods_are_not_checked", () => {
    for (const method of ["GET", "HEAD", "OPTIONS", "get"]) {
      expect(isSafeMethod(method)).toBe(true);
      expect(checkCsrf(request(method, { origin: "https://evil.example" }))).toEqual({ ok: true });
    }
  });

  it("test_AC_IDA_19_without_configured_origin_every_mutation_is_refused", () => {
    vi.stubEnv("HUB_APP_ORIGIN", "");
    expect(checkCsrf(legitimate())).toEqual({ ok: false, reason: "config" });
    expect(checkOrigin(new Headers({ "sec-fetch-site": "same-origin" }))).toEqual({
      ok: false,
      reason: "config",
    });
  });

  it("test_AC_IDA_19_origin_is_compared_with_the_normalized_app_origin", () => {
    vi.stubEnv("HUB_APP_ORIGIN", "HTTPS://App.Example.Test:443");
    expect(checkOrigin(new Headers({ origin: APP_ORIGIN }))).toEqual({ ok: true });
  });

  it("test_AC_IDA_19_token_check_alone_ignores_the_origin", () => {
    const headers = new Headers({ "x-csrf-token": TOKEN, cookie: `__Host-cpu_csrf=${TOKEN}` });
    expect(checkCsrfToken(headers)).toEqual({ ok: true });
  });

  it("test_AC_IDA_19_refusal_is_a_403_bff_csrf_failed_without_secrets", async () => {
    const check = checkCsrf(legitimate({ "x-csrf-token": "d".repeat(43) }));
    const response = csrfFailure(check, REQUEST_ID);

    expect(response).not.toBeNull();
    expect(response!.status).toBe(403);
    expect(response!.headers.get("content-type")).toBe("application/problem+json");
    expect(response!.headers.get("cache-control")).toBe("no-store");
    const text = await response!.text();
    expect(JSON.parse(text)).toMatchObject({ code: "bff.csrf_failed", request_id: REQUEST_ID });
    expect(text).not.toContain(TOKEN);
    expect(text).not.toContain("d".repeat(43));
  });

  it("test_AC_IDA_19_a_passed_check_returns_no_response", () => {
    expect(csrfFailure({ ok: true }, REQUEST_ID)).toBeNull();
  });
});

describe("cookie header parsing", () => {
  it("returns every value of a name, trimmed and in order", () => {
    const headers = new Headers({ cookie: " a=1;b=2 ; a = 3 ;broken; c==x" });
    expect(requestCookieValues(headers, "a")).toEqual(["1", "3"]);
    expect(requestCookieValues(headers, "b")).toEqual(["2"]);
    expect(requestCookieValues(headers, "c")).toEqual(["=x"]);
    expect(requestCookieValues(headers, "broken")).toEqual([]);
    expect(requestCookieValues(new Headers(), "a")).toEqual([]);
  });
});

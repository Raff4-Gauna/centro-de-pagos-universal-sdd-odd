// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as route from "./route";

const { POST, dynamic, runtime } = route;

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const CREDENTIAL = "test-only-bff-credential-sentinel";
const APP = "https://app.example";
const ACCESS = "eyJhbGciOiJFUzI1NiJ9.access-token-sentinel.sig";
const REFRESH = "rt1.c2lk.refresh-token-sentinel";
const CSRF = "c".repeat(43);
const ORG = "0b7f5b6e-1d2c-4f3a-9b8e-7c6d5e4f3a2b";
const SESSION_COOKIES = [
  `__Host-cpu_at=${ACCESS}`,
  `__Host-cpu_rt=${REFRESH}`,
  `__Host-cpu_csrf=${CSRF}`,
  `__Host-cpu_org=${ORG}`,
].join("; ");

const CLEARED = {
  "__Host-cpu_at": "__Host-cpu_at=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax",
  "__Host-cpu_rt": "__Host-cpu_rt=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax",
  "__Host-cpu_csrf": "__Host-cpu_csrf=; Max-Age=0; Path=/; Secure; SameSite=Lax",
  "__Host-cpu_org": "__Host-cpu_org=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax",
};

type Call = { path: string; body: Record<string, unknown>; headers: Headers; signal?: AbortSignal };

function mockDjango(
  reply: () => Response | Promise<Response> = () => new Response(null, { status: 204 }),
) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push({
      path: new URL(String(input)).pathname,
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
      headers: new Headers(init?.headers),
      signal: init?.signal ?? undefined,
    });
    return reply();
  });
  return calls;
}

function logout(
  cookie: string | null = SESSION_COOKIES,
  headers: Record<string, string> = { origin: APP, "x-csrf-token": CSRF },
  signal?: AbortSignal,
): Promise<Response> {
  const all = cookie === null ? headers : { ...headers, cookie };
  return POST(new Request(`${APP}/api/auth/logout`, { method: "POST", headers: all, signal }));
}

function setCookies(response: Response): Record<string, string> {
  return Object.fromEntries(
    response.headers.getSetCookie().map((line) => [line.slice(0, line.indexOf("=")), line]),
  );
}

async function visible(response: Response): Promise<string> {
  return [...response.headers.entries()].join("\n") + (await response.text());
}

beforeEach(() => {
  vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
  vi.stubEnv("HUB_BFF_CREDENTIAL", CREDENTIAL);
  vi.stubEnv("HUB_APP_ORIGIN", APP);
  vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "1");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("POST /api/auth/logout", () => {
  it("runs on Node.js and is never cached", () => {
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
    expect(Object.keys(route).sort()).toEqual(["POST", "dynamic", "runtime"]);
  });

  it("test_AC_IDA_17_logout_revokes_in_django_and_clears_the_session_cookies", async () => {
    const calls = mockDjango();

    const response = await logout();

    expect(response.status).toBe(204);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
    expect(setCookies(response)).toEqual(CLEARED);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.path).toBe("/api/auth/bff/logout/");
    expect(calls[0]!.body).toEqual({
      refresh_token: REFRESH,
      access_token: ACCESS,
      reason: "logout",
    });
    expect(calls[0]!.headers.get("x-hub-bff-credential")).toBe(CREDENTIAL);
  });

  it("test_AC_IDA_17_no_token_reaches_the_browser", async () => {
    mockDjango();

    const shown = await visible(await logout());

    for (const secret of [ACCESS, REFRESH, CSRF, ORG, CREDENTIAL]) {
      expect(shown).not.toContain(secret);
    }
  });

  it.each([
    ["a parse error", () => Response.json({ code: "parse_error" }, { status: 400 })],
    ["an unsupported media type", () => new Response(null, { status: 415 })],
    ["a server error", () => new Response(null, { status: 500 })],
    [
      "a network failure",
      () => {
        throw new TypeError("fetch failed");
      },
    ],
    [
      "a timeout",
      () => {
        throw new DOMException("timed out", "TimeoutError");
      },
    ],
  ])("test_AC_IDA_17_cookies_are_cleared_even_after_%s", async (_case, reply) => {
    mockDjango(reply);

    const response = await logout();

    expect(response.status).toBe(204);
    expect(setCookies(response)).toEqual(CLEARED);
  });

  it("test_AC_IDA_17_cookies_are_cleared_even_if_discarding_the_reply_fails", async () => {
    const body = new ReadableStream<Uint8Array>({
      cancel() {
        throw new Error("cancel failed");
      },
    });
    mockDjango(() => new Response(body, { status: 400 }));

    const response = await logout();

    expect(response.status).toBe(204);
    expect(setCookies(response)).toEqual(CLEARED);
  });

  it("test_AC_IDA_17_without_a_session_answers_204_and_does_not_call_django", async () => {
    const calls = mockDjango();

    const response = await logout(null, { origin: APP });

    expect(response.status).toBe(204);
    expect(setCookies(response)).toEqual(CLEARED);
    expect(calls).toHaveLength(0);
  });

  it("test_AC_IDA_17_a_second_logout_answers_204", async () => {
    mockDjango();
    const first = await logout();
    expect(first.status).toBe(204);

    const second = await logout(`__Host-cpu_org=${ORG}`, { "sec-fetch-site": "same-origin" });

    expect(second.status).toBe(204);
    expect(setCookies(second)).toEqual(CLEARED);
  });

  it("test_AC_IDA_35_logout_with_only_the_access_cookie_still_names_the_session", async () => {
    const calls = mockDjango();

    const response = await logout(`__Host-cpu_at=${ACCESS}; __Host-cpu_csrf=${CSRF}`);

    expect(response.status).toBe(204);
    expect(calls[0]!.body).toEqual({ refresh_token: null, access_token: ACCESS, reason: "logout" });
  });

  it("test_AC_IDA_17_a_repeated_refresh_cookie_is_not_sent_but_is_cleared", async () => {
    const calls = mockDjango();
    const cookie = `${SESSION_COOKIES}; __Host-cpu_rt=rt1.other.token`;

    const response = await logout(cookie);

    expect(response.status).toBe(204);
    expect(calls[0]!.body).toEqual({ refresh_token: null, access_token: ACCESS, reason: "logout" });
    expect(setCookies(response)).toEqual(CLEARED);
  });

  it("test_AC_IDA_17_the_revocation_is_not_cut_short_when_the_browser_leaves", async () => {
    const calls = mockDjango();
    const browser = new AbortController();
    browser.abort();

    const response = await logout(
      SESSION_COOKIES,
      { origin: APP, "x-csrf-token": CSRF },
      browser.signal,
    );

    expect(response.status).toBe(204);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.signal?.aborted).toBe(false);
  });

  it.each([
    ["without the CSRF header", { origin: APP }],
    ["with another CSRF token", { origin: APP, "x-csrf-token": "d".repeat(43) }],
    ["from another origin", { origin: "https://evil.example", "x-csrf-token": CSRF }],
    ["without Origin nor Sec-Fetch-Site", { "x-csrf-token": CSRF }],
  ])("test_AC_IDA_19_a_session_logout_%s_is_refused_without_django", async (_case, headers) => {
    const calls = mockDjango();

    const response = await logout(SESSION_COOKIES, headers);

    expect(response.status).toBe(403);
    expect(((await response.json()) as { code: string }).code).toBe("bff.csrf_failed");
    expect(response.headers.getSetCookie()).toEqual([]);
    expect(calls).toHaveLength(0);
  });

  it("test_AC_IDA_19_a_logout_without_session_from_another_site_is_refused", async () => {
    const calls = mockDjango();

    const response = await logout(`__Host-cpu_org=${ORG}`, { "sec-fetch-site": "cross-site" });

    expect(response.status).toBe(403);
    expect(response.headers.getSetCookie()).toEqual([]);
    expect(calls).toHaveLength(0);
  });
});

// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, dynamic, runtime } from "./route";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const CREDENTIAL = "test-only-bff-credential-sentinel";
const APP = "https://app.example";
const BINDING = "b".repeat(43);
const ACCESS = "eyJhbGciOiJFUzI1NiJ9.access-token-sentinel.sig";
const REFRESH = "rt1.c2lk.refresh-token-sentinel";
const CODE = "google-code-sentinel";
const STATE = "google-state-sentinel";

const SESSION = {
  access_token: ACCESS,
  access_expires_in: 900,
  refresh_token: REFRESH,
  session_id: "0b7f5b6e-1d2c-4f3a-9b8e-7c6d5e4f3a2b",
  session_expires_in: 604800,
  return_path: "/cobros",
};

type Call = { path: string; body: Record<string, unknown>; headers: Headers };

function mockDjango(complete: () => Response = () => Response.json(SESSION)) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = new URL(String(input)).pathname;
    calls.push({
      path,
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
      headers: new Headers(init?.headers),
    });
    return path === "/api/auth/bff/logout/" ? new Response(null, { status: 204 }) : complete();
  });
  return calls;
}

function problem(status: number, code: string): Response {
  return Response.json(
    { code, title: "x", status, detail: "secret detail" },
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

function callback(
  query = `?code=${CODE}&state=${STATE}`,
  cookie: string | null = `__Host-cpu_login=${BINDING}`,
  headers: Record<string, string> = {},
): Promise<Response> {
  const all = cookie === null ? headers : { ...headers, cookie };
  return GET(new Request(`http://bff.internal/api/auth/google/callback${query}`, { headers: all }));
}

function setCookies(response: Response): Record<string, string> {
  return Object.fromEntries(
    response.headers.getSetCookie().map((line) => [line.slice(0, line.indexOf("=")), line]),
  );
}

const CLEARED_LOGIN = "__Host-cpu_login=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax";

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
  vi.unstubAllEnvs();
});

describe("GET /api/auth/google/callback (RF-IDA-02, design.md §6.3)", () => {
  it("test_AC_IDA_01_sets_session_cookies_and_redirects_inside_the_app", async () => {
    const calls = mockDjango();

    const response = await callback(undefined, undefined, {
      "user-agent": "Mozilla/5.0 (X11; Linux x86_64)",
      "x-forwarded-for": "203.0.113.7",
    });

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(`${APP}/cobros`);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(calls).toHaveLength(1);
    expect(calls[0]!.path).toBe("/api/auth/bff/login/complete/");
    expect(calls[0]!.body).toEqual({
      state: STATE,
      login_binding: BINDING,
      code: CODE,
      error: null,
    });
    expect(calls[0]!.headers.get("x-hub-client-ip")).toBe("203.0.113.7");
    expect(calls[0]!.headers.get("x-hub-client-ua")).toBe("Mozilla/5.0 (X11; Linux x86_64)");
    const cookies = setCookies(response);
    expect(cookies["__Host-cpu_at"]).toBe(
      `__Host-cpu_at=${ACCESS}; Max-Age=840; Path=/; Secure; HttpOnly; SameSite=Lax`,
    );
    expect(cookies["__Host-cpu_rt"]).toBe(
      `__Host-cpu_rt=${REFRESH}; Max-Age=604800; Path=/; Secure; HttpOnly; SameSite=Lax`,
    );
    expect(cookies["__Host-cpu_csrf"]).toMatch(
      /^__Host-cpu_csrf=[A-Za-z0-9_-]{43}; Max-Age=604800; Path=\/; Secure; SameSite=Lax$/,
    );
    expect(cookies["__Host-cpu_login"]).toBe(CLEARED_LOGIN);
  });

  it("test_AC_IDA_18_no_token_in_the_body_nor_in_a_readable_cookie", async () => {
    mockDjango();

    const response = await callback();

    expect(await response.text()).toBe("");
    for (const line of response.headers.getSetCookie()) {
      if (line.includes(ACCESS) || line.includes(REFRESH)) {
        expect(line).toContain("HttpOnly");
        expect(line).toContain("Secure");
        expect(line).toContain("SameSite=Lax");
      }
    }
    expect(response.headers.get("location")).not.toContain(ACCESS);
    expect(response.headers.get("location")).not.toContain(REFRESH);
  });

  it.each([
    ["absolute", "https://evil.example/x"],
    ["network path", "//evil.example/x"],
    ["dot segments", "/..//evil.example"],
    ["backslash", "/\\evil.example"],
    ["not a string", null],
  ])("test_AC_IDA_19_hostile_return_path_lands_on_inicio_%s", async (_name, returnPath) => {
    mockDjango(() => Response.json({ ...SESSION, return_path: returnPath }));

    const response = await callback();

    expect(response.headers.get("location")).toBe(`${APP}/`);
  });

  it("test_RF_IDA_02_previous_session_is_superseded_best_effort", async () => {
    const calls = mockDjango();

    const response = await callback(
      undefined,
      `__Host-cpu_login=${BINDING}; __Host-cpu_rt=rt1.old; __Host-cpu_at=old.jwt`,
    );

    expect(calls.map((call) => call.path)).toEqual([
      "/api/auth/bff/login/complete/",
      "/api/auth/bff/logout/",
    ]);
    expect(calls[1]!.body).toEqual({
      refresh_token: "rt1.old",
      access_token: "old.jwt",
      reason: "superseded",
    });
    expect(response.headers.get("location")).toBe(`${APP}/cobros`);
  });

  it("test_RF_IDA_02_failed_superseding_logout_keeps_the_new_session", async () => {
    let first = true;
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      if (first) {
        first = false;
        return Response.json(SESSION);
      }
      throw new TypeError("fetch failed");
    });

    const response = await callback(undefined, `__Host-cpu_login=${BINDING}; __Host-cpu_rt=old`);

    expect(response.headers.get("location")).toBe(`${APP}/cobros`);
    expect(setCookies(response)["__Host-cpu_rt"]).toContain(REFRESH);
  });

  it.each([
    [400, "login_cancelled", "login_cancelled"],
    [400, "google_auth_failed", "google_auth_failed"],
    [400, "validation_error", "google_auth_failed"],
    [403, "not_invited", "not_invited"],
    [403, "email_not_verified", "email_not_verified"],
    [403, "user_inactive", "user_inactive"],
    [409, "identity_conflict", "identity_conflict"],
    [429, "rate_limited", "rate_limited"],
    [503, "google_unavailable", "google_unavailable"],
    [503, "login_disabled", "login_disabled"],
    [500, "internal_error", "internal_error"],
    [418, "something_new", "internal_error"],
  ])("test_AC_IDA_19_django_%i_%s_goes_to_login_with_%s", async (status, code, expected) => {
    mockDjango(() => problem(status, code));

    const response = await callback();

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(`${APP}/login?error=${expected}`);
    expect(setCookies(response)).toEqual({ "__Host-cpu_login": CLEARED_LOGIN });
    const shown = await visible(response);
    for (const secret of [CODE, STATE, BINDING, CREDENTIAL, "secret detail"]) {
      expect(shown).not.toContain(secret);
    }
  });

  it.each([
    ["access_denied", "access_denied"],
    ["server_error", "provider_error"],
    [encodeURIComponent("<script>x</script>"), "provider_error"],
  ])("test_RF_IDA_02_google_error_%s_is_relayed_as_%s", async (error, relayed) => {
    const calls = mockDjango(() => problem(400, "login_cancelled"));

    await callback(`?error=${error}&state=${STATE}`);

    expect(calls[0]!.body).toEqual({
      state: STATE,
      login_binding: BINDING,
      code: null,
      error: relayed,
    });
  });

  it.each([
    ["no cookie", null],
    ["another shape", "__Host-cpu_login=short"],
    ["repeated", `__Host-cpu_login=${BINDING}; __Host-cpu_login=${"c".repeat(43)}`],
  ])("test_RF_IDA_02_callback_without_binding_never_calls_django_%s", async (_name, cookie) => {
    const calls = mockDjango();

    const response = await callback(undefined, cookie);

    expect(calls).toHaveLength(0);
    expect(response.headers.get("location")).toBe(`${APP}/login?error=google_auth_failed`);
    expect(setCookies(response)).toEqual({ "__Host-cpu_login": CLEARED_LOGIN });
  });

  it("test_RF_IDA_02_missing_state_is_sent_empty", async () => {
    const calls = mockDjango(() => problem(400, "google_auth_failed"));

    await callback(`?code=${CODE}`);

    expect(calls[0]!.body.state).toBe("");
  });

  it.each([
    ["not json", () => new Response("<html>", { status: 200 })],
    ["no refresh token", () => Response.json({ ...SESSION, refresh_token: "" })],
    ["negative lifetime", () => Response.json({ ...SESSION, access_expires_in: -1 })],
    ["token with a separator", () => Response.json({ ...SESSION, access_token: "a;b" })],
  ])("test_AC_IDA_18_unusable_session_sets_no_session_cookie_%s", async (_name, reply) => {
    mockDjango(reply);

    const response = await callback();

    expect(response.headers.get("location")).toBe(`${APP}/login?error=internal_error`);
    expect(setCookies(response)).toEqual({ "__Host-cpu_login": CLEARED_LOGIN });
  });

  it("test_RF_IDA_02_unreachable_django_goes_to_login_with_internal_error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));

    const response = await callback();

    expect(response.headers.get("location")).toBe(`${APP}/login?error=internal_error`);
    expect(setCookies(response)).toEqual({ "__Host-cpu_login": CLEARED_LOGIN });
  });

  it("test_C_06_missing_origin_never_opens_a_session", async () => {
    const calls = mockDjango();
    vi.stubEnv("HUB_APP_ORIGIN", "");

    const response = await callback();

    expect(calls).toHaveLength(0);
    expect(response.headers.get("location")).toBe("/login?error=internal_error");
  });

  it("test_RF_IDA_02_route_is_dynamic_on_node_runtime", () => {
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });
});

// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, dynamic, runtime } from "./route";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const CREDENTIAL = "test-only-bff-credential-sentinel";
const APP = "https://app.example";
const GOOGLE = "https://accounts.google.com/o/oauth2/v2/auth?client_id=x&state=s";
const BINDING = "b".repeat(43);

type Call = { url: URL; body: Record<string, unknown>; headers: Headers };

function mockDjango(impl: () => Response = () => Response.json({ authorization_url: GOOGLE })) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push({
      url: new URL(String(input)),
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
      headers: new Headers(init?.headers),
    });
    return impl();
  });
  return calls;
}

function problem(status: number, code: string): Response {
  return Response.json(
    { code, title: "x", status, detail: "secret detail" },
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

function start(query = "", headers: Record<string, string> = {}): Promise<Response> {
  return GET(new Request(`http://bff.internal/api/auth/google/start${query}`, { headers }));
}

function setCookies(response: Response): string[] {
  return response.headers.getSetCookie();
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

describe("GET /api/auth/google/start (RF-IDA-01, design.md §6.3)", () => {
  it("test_RF_IDA_01_redirects_to_google_with_a_new_binding_cookie", async () => {
    const calls = mockDjango();

    const response = await start("?return_to=/cobros", { "x-forwarded-for": "203.0.113.7" });

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(new URL(GOOGLE).href);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(await response.text()).toBe("");
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url.pathname).toBe("/api/auth/bff/login/start/");
    expect(calls[0]!.headers.get("x-hub-client-ip")).toBe("203.0.113.7");
    const binding = calls[0]!.body.login_binding as string;
    expect(binding).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(calls[0]!.body.return_path).toBe("/cobros");
    expect(setCookies(response)).toEqual([
      `__Host-cpu_login=${binding}; Max-Age=600; Path=/; Secure; HttpOnly; SameSite=Lax`,
    ]);
  });

  it("test_RF_IDA_01_reuses_the_binding_of_a_pending_attempt", async () => {
    const calls = mockDjango();

    const response = await start("", { cookie: `other=1; __Host-cpu_login=${BINDING}` });

    expect(calls[0]!.body).toEqual({ login_binding: BINDING });
    expect(setCookies(response)[0]).toContain(`__Host-cpu_login=${BINDING};`);
  });

  it("test_RF_IDA_01_ignores_a_binding_cookie_of_another_shape", async () => {
    const calls = mockDjango();

    await start("", { cookie: "__Host-cpu_login=short" });

    expect(calls[0]!.body.login_binding).not.toBe("short");
    expect(calls[0]!.body.login_binding).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("test_AC_IDA_19_hostile_return_to_is_sanitized_before_django", async () => {
    const calls = mockDjango();

    await start(`?return_to=${encodeURIComponent("//evil.example/x")}`);

    expect(calls[0]!.body.return_path).toBe("/");
  });

  it.each([
    [429, "rate_limited", "rate_limited"],
    [503, "login_disabled", "login_disabled"],
    [400, "validation_error", "internal_error"],
    [500, "internal_error", "internal_error"],
  ])("test_RF_IDA_01_django_%i_%s_goes_to_login_with_%s", async (status, code, expected) => {
    mockDjango(() => problem(status, code));

    const response = await start("?return_to=/cobros");

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(`${APP}/login?error=${expected}`);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(setCookies(response)).toEqual([]);
  });

  it("test_RF_IDA_01_unreachable_django_goes_to_login_with_internal_error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));

    const response = await start();

    expect(response.headers.get("location")).toBe(`${APP}/login?error=internal_error`);
  });

  it.each([
    ["no url", {}],
    ["not a string", { authorization_url: 7 }],
    ["not a url", { authorization_url: "nope" }],
    ["another scheme", { authorization_url: "javascript:alert(1)" }],
  ])("test_RF_IDA_01_unusable_authorization_url_is_refused_%s", async (_name, body) => {
    mockDjango(() => Response.json(body));

    const response = await start();

    expect(response.headers.get("location")).toBe(`${APP}/login?error=internal_error`);
    expect(setCookies(response)).toEqual([]);
  });

  it("test_C_06_missing_configuration_never_calls_django_nor_leaks", async () => {
    const calls = mockDjango();
    vi.stubEnv("HUB_APP_ORIGIN", "");

    const response = await start();

    expect(calls).toHaveLength(0);
    expect(response.headers.get("location")).toBe("/login?error=internal_error");
  });

  it("test_C_06_invalid_proxy_hops_never_calls_django", async () => {
    const calls = mockDjango();
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "many");

    const response = await start();

    expect(calls).toHaveLength(0);
    expect(response.headers.get("location")).toBe(`${APP}/login?error=internal_error`);
  });

  it("test_C_06_credential_never_reaches_the_response", async () => {
    mockDjango(() => problem(503, "login_disabled"));

    const response = await start();

    const visible = [...response.headers.entries()].join("\n") + (await response.text());
    expect(visible).not.toContain(CREDENTIAL);
    expect(visible).not.toContain("secret detail");
  });

  it("test_RF_IDA_01_route_is_dynamic_on_node_runtime", () => {
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });
});

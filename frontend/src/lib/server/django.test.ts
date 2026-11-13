// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DJANGO_BFF_TIMEOUT_MS, callDjangoBff } from "./django";
import { bffProblem } from "./problem";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const CREDENTIAL = "test-only-bff-credential-sentinel";
const BINDING = "A".repeat(43);
const REQUEST_ID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";
const PATH = "/api/auth/bff/login/start/" as const;

type Call = { url: URL; init: RequestInit };

function mockDjango(impl: () => Promise<Response> = async () => Response.json({ ok: true })) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push({ url: new URL(String(input)), init: init ?? {} });
    return impl();
  });
  return calls;
}

function sentHeaders(call: Call): Record<string, string> {
  return Object.fromEntries(new Headers(call.init.headers).entries());
}

function start(returnPath?: string | null, extra: object = {}) {
  return callDjangoBff({
    path: PATH,
    body:
      returnPath === undefined
        ? { login_binding: BINDING }
        : { login_binding: BINDING, return_path: returnPath },
    requestId: REQUEST_ID,
    ...extra,
  });
}

beforeEach(() => {
  vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
  vi.stubEnv("HUB_BFF_CREDENTIAL", CREDENTIAL);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("BFF client to Django auth/bff/* (RN-IDA-12, design.md §6.1)", () => {
  it("test_RN_IDA_12_sends_credential_forwarded_proto_and_client_headers", async () => {
    const calls = mockDjango();
    const outcome = await start(undefined, {
      clientIp: "203.0.113.7",
      clientUserAgent: "Mozilla/5.0 (X11; Linux x86_64)",
    });

    expect(outcome.kind).toBe("response");
    expect(calls).toHaveLength(1);
    const [call] = calls;
    expect(call!.url.href).toBe("http://backend:8000/api/auth/bff/login/start/");
    expect(call!.init).toMatchObject({ method: "POST", redirect: "manual", cache: "no-store" });
    expect(sentHeaders(call!)).toEqual({
      accept: "application/json",
      "content-type": "application/json",
      "x-request-id": REQUEST_ID,
      // Q-065: without it SECURE_SSL_REDIRECT answers 301 in prod.
      "x-forwarded-proto": "https",
      "x-hub-bff-credential": CREDENTIAL,
      "x-hub-client-ip": "203.0.113.7",
      "x-hub-client-ua": "Mozilla/5.0 (X11; Linux x86_64)",
    });
    expect(JSON.parse(String(call!.init.body))).toEqual({ login_binding: BINDING });
  });

  it("test_RN_IDA_12_client_headers_are_left_out_when_unknown_or_unsafe", async () => {
    const calls = mockDjango();
    await start(undefined, { clientIp: null, clientUserAgent: "bad\r\nx-injected: 1" });
    await start(undefined, { clientUserAgent: "x".repeat(2000) });
    await start(undefined, { clientIp: "203.0.113.7\u0000", clientUserAgent: "Navegador 😀" });
    const [first, second, third] = calls.map(sentHeaders);
    expect(first).not.toHaveProperty("x-hub-client-ip");
    expect(first).not.toHaveProperty("x-hub-client-ua");
    expect(second!["x-hub-client-ua"]).toHaveLength(512);
    expect(third).not.toHaveProperty("x-hub-client-ip");
    expect(third).not.toHaveProperty("x-hub-client-ua");
  });

  it("test_AC_IDA_19_return_path_is_sanitized_before_django", async () => {
    const calls = mockDjango();
    // U+0000 would be a 400 from DRF: the person lands on "Inicio" instead.
    await start("/cobros\u0000");
    await start("//evil.example");
    await start("/%2F%2Fevil.example");
    await start("/cobros?tab=1");
    await start(null);
    const sent = calls.map((call) => JSON.parse(String(call.init.body)).return_path);
    expect(sent).toEqual(["/", "/", "/%2F%2Fevil.example", "/cobros?tab=1", null]);
  });

  it("test_RN_IDA_12_credential_never_leaves_in_errors_or_outcomes", async () => {
    mockDjango(async () => {
      throw new TypeError(`fetch failed ${CREDENTIAL}`);
    });
    const outcome = await start();
    expect(outcome).toEqual({ kind: "unavailable", reason: "network" });
    expect(JSON.stringify(outcome)).not.toContain(CREDENTIAL);

    vi.stubEnv("HUB_BFF_CREDENTIAL", "");
    const calls = mockDjango();
    expect(await start()).toEqual({ kind: "unavailable", reason: "config" });
    vi.stubEnv("BACKEND_INTERNAL_URL", "not a url");
    vi.stubEnv("HUB_BFF_CREDENTIAL", CREDENTIAL);
    expect(await start()).toEqual({ kind: "unavailable", reason: "config" });
    // Misconfigured: Django is never called (and so never without the credential).
    expect(calls).toHaveLength(0);
  });

  it("test_RN_IDA_12_timeout_and_client_abort_are_told_apart", async () => {
    mockDjango(async () => {
      throw new DOMException("timed out", "TimeoutError");
    });
    expect(await start()).toEqual({ kind: "unavailable", reason: "timeout" });

    const browser = new AbortController();
    browser.abort();
    mockDjango(async () => {
      throw new DOMException("aborted", "AbortError");
    });
    expect(await start(undefined, { signal: browser.signal })).toEqual({
      kind: "unavailable",
      reason: "client_abort",
    });
    expect(DJANGO_BFF_TIMEOUT_MS).toBe(15_000);
  });

  it("test_RN_IDA_12_django_answer_is_returned_as_is", async () => {
    mockDjango(async () =>
      Response.json({ code: "rate_limited" }, { status: 429, headers: { "retry-after": "60" } }),
    );
    const outcome = await start();
    expect(outcome.kind).toBe("response");
    if (outcome.kind === "response") {
      expect(outcome.response.status).toBe(429);
      expect(outcome.response.headers.get("retry-after")).toBe("60");
    }
  });
});

describe("BFF problem responses (design.md §6.3)", () => {
  it("test_RN_IDA_13_csrf_problem_is_403_problem_json_no_store", async () => {
    const response = bffProblem("bff.csrf_failed", REQUEST_ID);
    expect(response.status).toBe(403);
    expect(Object.fromEntries(response.headers.entries())).toEqual({
      "content-type": "application/problem+json",
      "cache-control": "no-store",
      "x-request-id": REQUEST_ID,
    });
    expect(await response.json()).toMatchObject({
      type: "urn:hub:problem:bff.csrf_failed",
      status: 403,
      code: "bff.csrf_failed",
      request_id: REQUEST_ID,
    });
  });

  it("test_RN_IDA_12_upstream_problems_carry_no_detail", async () => {
    for (const [code, status] of [
      ["bff.upstream_unavailable", 502],
      ["bff.upstream_timeout", 504],
    ] as const) {
      const response = bffProblem(code, REQUEST_ID);
      expect(response.status).toBe(status);
      expect(await response.json()).not.toHaveProperty("detail");
    }
  });
});

// @vitest-environment node
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE, GET, PATCH, POST, PUT, dynamic, runtime } from "@/app/api/[...path]/route";

import { proxyToBackend } from "./backend-proxy";
import { getBackendInternalUrl } from "./env";

// `server-only` throws outside the react-server condition; that the modules import it is
// asserted on their source below.
vi.mock("server-only", () => ({}));

const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const VALID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";
const BFF = "http://localhost:3000";

type FetchCall = { url: URL; init: RequestInit };

function mockBackend(makeResponse: () => Response = () => Response.json({ ok: true })) {
  const calls: FetchCall[] = [];
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push({ url: new URL(String(input)), init: init ?? {} });
    return makeResponse();
  });
  return { calls, spy };
}

function forwardedHeaders(call: FetchCall): Record<string, string> {
  return Object.fromEntries(new Headers(call.init.headers).entries());
}

function captureStdout(): string[] {
  const lines: string[] = [];
  vi.spyOn(process.stdout, "write").mockImplementation((chunk: string | Uint8Array) => {
    lines.push(String(chunk));
    return true;
  });
  return lines;
}

function routeContext(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

beforeEach(() => {
  vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
  captureStdout();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("BFF pass-through (AC-PLT-10, RN-PLT-16, RF-PLT-06)", () => {
  it("test_AC_PLT_10_bff_generates_request_id_when_missing_forwards_and_returns_it", async () => {
    const { calls } = mockBackend(
      () =>
        new Response('{"detail":"x"}', {
          status: 404,
          headers: { "content-type": "application/problem+json" },
        }),
    );

    const response = await GET(new Request(`${BFF}/api/__smoke__`), routeContext(["__smoke__"]));

    expect(calls).toHaveLength(1);
    const sent = forwardedHeaders(calls[0]!)["x-request-id"];
    expect(sent).toMatch(UUID4);
    // The same id the backend received is the one the browser gets back.
    expect(response.headers.get("x-request-id")).toBe(sent);
    expect(calls[0]!.url.href).toBe("http://backend:8000/api/__smoke__");
    // Status, content type and body pass through untouched.
    expect(response.status).toBe(404);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
    expect(await response.text()).toBe('{"detail":"x"}');

    // A valid incoming id is kept end to end; an invalid one is replaced (AC-PLT-09).
    const kept = await GET(
      new Request(`${BFF}/api/__smoke__`, { headers: { "x-request-id": VALID } }),
      routeContext(["__smoke__"]),
    );
    expect(forwardedHeaders(calls[1]!)["x-request-id"]).toBe(VALID);
    expect(kept.headers.get("x-request-id")).toBe(VALID);

    const replaced = await GET(
      new Request(`${BFF}/api/__smoke__`, { headers: { "x-request-id": "bad id" } }),
      routeContext(["__smoke__"]),
    );
    const newId = forwardedHeaders(calls[2]!)["x-request-id"];
    expect(newId).toMatch(UUID4);
    expect(replaced.headers.get("x-request-id")).toBe(newId);

    // A valid upper-case id is normalized to lower case, the same as the backend (T-PLT-12).
    const upper = await GET(
      new Request(`${BFF}/api/__smoke__`, { headers: { "x-request-id": VALID.toUpperCase() } }),
      routeContext(["__smoke__"]),
    );
    expect(forwardedHeaders(calls[3]!)["x-request-id"]).toBe(VALID);
    expect(upper.headers.get("x-request-id")).toBe(VALID);

    // Route segment config and every method go through the same proxy.
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
    expect(new Set([GET, POST, PUT, PATCH, DELETE]).size).toBe(1);
  });

  it("test_RN_PLT_16_bff_forwards_only_allowlisted_headers_never_cookie", async () => {
    const { calls } = mockBackend();
    const body = '{"amount":"10.00"}';

    const incoming = new Request(`${BFF}/api/charges`, {
      method: "POST",
      body,
      headers: {
        accept: "application/json",
        "accept-language": "es-AR",
        "content-type": "application/json",
        "content-length": String(body.length),
        "x-request-id": VALID,
        cookie: "session=abc",
        authorization: "Bearer from-the-browser",
        "x-forwarded-for": "10.0.0.1",
        "x-api-key": "k",
        origin: "http://evil.example",
      },
    });
    // Precondition: the runtime does keep the cookie on the incoming request.
    expect(incoming.headers.get("cookie")).toBe("session=abc");

    await proxyToBackend(incoming, ["charges"]);

    expect(calls).toHaveLength(1);
    expect(forwardedHeaders(calls[0]!)).toEqual({
      accept: "application/json",
      "accept-language": "es-AR",
      "content-type": "application/json",
      // Kept so Django/gunicorn get a sized body instead of `Transfer-Encoding: chunked`.
      "content-length": String(body.length),
      "x-request-id": VALID,
    });
    expect(calls[0]!.init.method).toBe("POST");
    // The body is streamed as-is, not parsed or rewritten.
    expect(await new Response(calls[0]!.init.body).text()).toBe(body);
    expect(calls[0]!.init.redirect).toBe("manual");
    expect((calls[0]!.init as RequestInit & { duplex?: string }).duplex).toBe("half");
    expect(calls[0]!.init.cache).toBe("no-store");

    // A body whose content-length is missing or not plain digits never reaches the backend
    // (Django would read it as empty): 411 bff.length_required, covered in the errors suite.
    for (const contentLength of ["12, 12", "-1", "1e3", "0x12", "abc"]) {
      const response = await proxyToBackend(
        new Request(`${BFF}/api/charges`, {
          method: "POST",
          body,
          headers: { "content-length": contentLength },
        }),
        ["charges"],
      );
      expect(response.status, contentLength).toBe(411);
    }
    expect(calls).toHaveLength(1);
    // Without a body, content-length is never sent.
    await proxyToBackend(
      new Request(`${BFF}/api/charges`, { headers: { "content-length": "18" } }),
      ["charges"],
    );
    expect(calls).toHaveLength(2);
    expect(forwardedHeaders(calls[1]!)).not.toHaveProperty("content-length");
    expect(calls[1]!.init.body).toBeUndefined();
  });

  it("test_RN_PLT_16_bff_strips_set_cookie", async () => {
    const upstream = new Response("payload", {
      status: 201,
      headers: {
        "content-type": "text/csv",
        "set-cookie": "sessionid=backend; HttpOnly",
        "retry-after": "5",
        "content-disposition": 'attachment; filename="r.csv"',
        "cache-control": "no-store",
        "x-request-id": "11111111-1111-4111-8111-111111111111",
        "x-powered-by": "django",
        server: "gunicorn",
        "access-control-allow-origin": "*",
      },
    });
    // Precondition: the upstream response really carries a Set-Cookie.
    expect(upstream.headers.getSetCookie()).toEqual(["sessionid=backend; HttpOnly"]);
    mockBackend(() => upstream);

    const response = await proxyToBackend(
      new Request(`${BFF}/api/reports`, { headers: { "x-request-id": VALID } }),
      ["reports"],
    );

    expect(Object.fromEntries(response.headers.entries())).toEqual({
      "content-type": "text/csv",
      "retry-after": "5",
      "content-disposition": 'attachment; filename="r.csv"',
      "cache-control": "no-store",
      // Always the BFF's own id, never a different one coming from upstream.
      "x-request-id": VALID,
    });
    expect(response.headers.getSetCookie()).toEqual([]);
    expect(response.status).toBe(201);
    expect(await response.text()).toBe("payload");
  });

  it("test_RN_PLT_16_bff_preserves_query_string", async () => {
    // What is preserved is the query's meaning (same pairs, same order, repeated keys), not its
    // bytes: in the real server Next re-serializes the query before the handler (`a%20b` -> `a+b`,
    // `%zz` -> `%25zz`), and both spellings decode to the same values in Django.
    const { calls } = mockBackend();
    const expected = [
      ["status", "paid"],
      ["page", "2"],
      ["q", "a b"],
      ["q", "c"],
    ];

    for (const query of ["status=paid&page=2&q=a%20b&q=c", "status=paid&page=2&q=a+b&q=c"]) {
      await proxyToBackend(new Request(`${BFF}/api/charges/list?${query}`), ["charges", "list"]);
    }

    for (const call of calls) {
      expect(call.url.pathname).toBe("/api/charges/list");
      expect([...call.url.searchParams]).toEqual(expected);
    }
    // The BFF itself copies the search string as it gets it.
    expect(calls[0]!.url.search).toBe("?status=paid&page=2&q=a%20b&q=c");
  });

  it("test_RF_PLT_06_bff_logs_one_json_line_without_path", async () => {
    mockBackend(() => new Response(null, { status: 503 }));
    const lines = captureStdout();

    const response = await proxyToBackend(
      new Request(`${BFF}/api/webhooks/unguessable-token-42?signature=s3cr3t`, {
        method: "DELETE",
      }),
      ["webhooks", "unguessable-token-42"],
    );

    expect(lines).toHaveLength(1);
    expect(lines[0]!.endsWith("\n")).toBe(true);
    expect(lines[0]!.trimEnd()).not.toContain("\n");
    const entry = JSON.parse(lines[0]!) as Record<string, unknown>;
    expect(entry).toEqual({
      timestamp: expect.any(String),
      level: "error",
      component: "bff",
      event: "bff.request",
      request_id: response.headers.get("x-request-id"),
      method: "DELETE",
      route: "/api/[...path]",
      status: 503,
      duration_ms: expect.any(Number),
    });
    expect(Number.isNaN(Date.parse(entry.timestamp as string))).toBe(false);
    // Neither the raw path nor the query string reach the log (C-06, C-16, Q-041).
    expect(lines[0]).not.toContain("unguessable-token-42");
    expect(lines[0]).not.toContain("webhooks");
    expect(lines[0]).not.toContain("signature");
    expect(lines[0]).not.toContain("s3cr3t");
  });

  it("test_RN_PLT_16_backend_url_read_at_runtime_server_only", async () => {
    const { calls } = mockBackend();

    // Read on every request, not frozen at import/build time.
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend-a:8000");
    await proxyToBackend(new Request(`${BFF}/api/x`), ["x"]);
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend-b:9000");
    await proxyToBackend(new Request(`${BFF}/api/x`), ["x"]);
    expect(calls.map((call) => call.url.origin)).toEqual([
      "http://backend-a:8000",
      "http://backend-b:9000",
    ]);

    // Validated, and the error never echoes the configured value.
    vi.stubEnv("BACKEND_INTERNAL_URL", "");
    expect(() => getBackendInternalUrl()).toThrow("BACKEND_INTERNAL_URL is not set");
    vi.stubEnv("BACKEND_INTERNAL_URL", "not a url sentinel-value");
    expect(() => getBackendInternalUrl()).toThrow(/^BACKEND_INTERNAL_URL is not a valid/);
    expect(() => getBackendInternalUrl()).not.toThrow(/sentinel-value/);
    vi.stubEnv("BACKEND_INTERNAL_URL", "ftp://backend:21");
    expect(() => getBackendInternalUrl()).toThrow(/^BACKEND_INTERNAL_URL is not a valid/);

    // Every lib/server module is guarded by `server-only` and no NEXT_PUBLIC_ variable exists.
    const here = dirname(fileURLToPath(import.meta.url));
    for (const name of ["env", "request-id", "backend-proxy", "log"]) {
      const source = readFileSync(join(here, `${name}.ts`), "utf8");
      const firstStatement = source.split("\n").find((line) => line && !line.startsWith("//"));
      expect(firstStatement, name).toBe('import "server-only";');
      expect(source, name).not.toContain("NEXT_PUBLIC_");
    }
    const route = readFileSync(join(here, "../../app/api/[...path]/route.ts"), "utf8");
    expect(route).not.toContain("NEXT_PUBLIC_");
    expect(route).not.toContain("process.env");
  });
});

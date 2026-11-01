// @vitest-environment node
import { createServer, type IncomingHttpHeaders, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UPSTREAM_TIMEOUT_MS, isSafeBackendTarget, proxyToBackend } from "./backend-proxy";

// `server-only` throws outside the react-server condition; the guard is checked in
// backend-proxy.test.ts (test_RN_PLT_16_backend_url_read_at_runtime_server_only).
vi.mock("server-only", () => ({}));

const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const VALID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";
const BFF = "http://localhost:3000";

let stdout: string[] = [];

beforeEach(() => {
  vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
  stdout = [];
  vi.spyOn(process.stdout, "write").mockImplementation((chunk: string | Uint8Array) => {
    stdout.push(String(chunk));
    return true;
  });
});

afterEach(async () => {
  vi.unstubAllEnvs();
  await Promise.all(servers.splice(0).map((close) => close()));
});

function mockFetch(impl: (init: RequestInit) => Promise<Response> = async () => Response.json({})) {
  const calls: { url: URL; init: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push({ url: new URL(String(input)), init: init ?? {} });
    return impl(init ?? {});
  });
  return calls;
}

function lastLog(): Record<string, unknown> {
  expect(stdout).toHaveLength(1);
  return JSON.parse(stdout[0]!) as Record<string, unknown>;
}

async function expectProblem(response: Response, status: number, code: string): Promise<string> {
  expect(response.status).toBe(status);
  const requestId = response.headers.get("x-request-id");
  expect(requestId).toMatch(UUID4);
  expect(Object.fromEntries(response.headers.entries())).toEqual({
    "content-type": "application/problem+json",
    "cache-control": "no-store",
    "x-request-id": requestId,
  });
  const text = await response.text();
  const body = JSON.parse(text) as Record<string, unknown>;
  expect(body).toMatchObject({
    type: `urn:hub:problem:${code}`,
    title: expect.any(String),
    status,
    code,
    request_id: requestId,
  });
  // The log line is written on errors too, with the same id and the problem code.
  expect(lastLog()).toMatchObject({
    level: status >= 500 ? "error" : "info",
    request_id: requestId,
    route: "/api/[...path]",
    status,
    code,
  });
  stdout.length = 0;
  return text;
}

// Real HTTP backend on 127.0.0.1 so undici's actual behaviour (content-length, abort) is tested.
type Received = { url: string; headers: IncomingHttpHeaders; body: string };
const servers: (() => Promise<void>)[] = [];

async function startBackend(reply: (res: ServerResponse) => void = (res) => res.end("{}")) {
  const received: Received[] = [];
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      received.push({
        url: req.url ?? "",
        headers: req.headers,
        body: Buffer.concat(chunks).toString(),
      });
      reply(res);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const close = () =>
    new Promise<void>((resolve) => {
      server.closeAllConnections();
      server.close(() => resolve());
    });
  servers.push(close);
  const { port } = server.address() as AddressInfo;
  return { origin: `http://127.0.0.1:${port}`, received, close };
}

describe("BFF path validation (RN-PLT-16)", () => {
  it("test_RN_PLT_16_bff_rejects_dotdot_and_encoded_separators", async () => {
    const calls = mockFetch();
    const vectors: string[][] = [
      ["..", "admin"],
      ["%2e%2e", "readyz"],
      [".%2E", "x"],
      ["%2E."],
      ["x", "..", "..", "metrics"],
      ["."],
      ["%2e"],
      ["", "evil.com"], // `//evil.com`
      ["//evil.com"],
      ["%2f%2fevil.com"],
      ["%252e%252e"], // double encoding
      ["%252e%252e", "readyz"],
      ["a%252fb"],
      ["a%255cb"],
      ["a%2fb"],
      ["a%2Fb"],
      ["a%5cb"],
      ["a%5Cb"],
      ["a/b"],
      ["a\\b"],
      ["x", "", "y"], // `/api/x//y` (a trailing empty segment is a trailing slash instead)
      ["%zz"], // malformed percent-encoding
      ["%252525252541"], // encoded more times than the BFF is willing to unwrap
      ["a\u0000b"],
      ["a\r\nb"],
    ];

    for (const segments of vectors) {
      const response = await proxyToBackend(
        new Request(`${BFF}/api/whatever`, { headers: { "x-request-id": VALID } }),
        segments,
      );
      const body = await expectProblem(response, 400, "bff.bad_path");
      expect(response.headers.get("x-request-id"), segments.join("/")).toBe(VALID);
      expect(JSON.parse(body)).toEqual({
        type: "urn:hub:problem:bff.bad_path",
        title: expect.any(String),
        status: 400,
        code: "bff.bad_path",
        detail: expect.any(String),
        request_id: VALID,
      });
    }
    expect(calls).toHaveLength(0);
  });

  it("test_RN_PLT_16_bff_encodes_each_segment_and_keeps_backend_origin", async () => {
    const calls = mockFetch();
    const cases: [string[], string][] = [
      [["@evil.com"], "http://backend:8000/api/%40evil.com"],
      [["a#b", "c?d=1"], "http://backend:8000/api/a%23b/c%3Fd%3D1"],
      [["a b", "ñ"], "http://backend:8000/api/a%20b/%C3%B1"],
      [["http:", "evil.com"], "http://backend:8000/api/http%3A/evil.com"],
      [["v1.2", "..x"], "http://backend:8000/api/v1.2/..x"],
    ];

    for (const [segments] of cases) {
      const response = await proxyToBackend(new Request(`${BFF}/api/whatever`), segments);
      expect(response.status).toBe(200);
    }
    expect(calls.map((call) => call.url.href)).toEqual(cases.map(([, href]) => href));
  });

  it("test_RN_PLT_16_bff_rejects_cross_origin_target", () => {
    const base = new URL("http://backend:8000");
    expect(isSafeBackendTarget(new URL("http://backend:8000/api/x"), base)).toBe(true);
    expect(isSafeBackendTarget(new URL("http://backend:8000/api/x/?q=1"), base)).toBe(true);
    for (const href of [
      "http://evil.com/api/x",
      "http://backend:8001/api/x",
      "https://backend:8000/api/x",
      "http://backend.evil.com:8000/api/x",
      "http://backend:8000/readyz",
      "http://backend:8000/api",
      "http://backend:8000/apix/",
      "http://backend:8000/metrics",
    ]) {
      expect(isSafeBackendTarget(new URL(href), base), href).toBe(false);
    }
  });

  it("test_RN_PLT_16_bff_keeps_trailing_slash", async () => {
    const calls = mockFetch();

    await proxyToBackend(new Request(`${BFF}/api/charges/`), ["charges"]);
    await proxyToBackend(new Request(`${BFF}/api/charges/?page=2`), ["charges"]);
    await proxyToBackend(new Request(`${BFF}/api/charges/`), ["charges", ""]);
    await proxyToBackend(new Request(`${BFF}/api/charges`), ["charges"]);
    await proxyToBackend(new Request(`${BFF}/api/a/b/`), ["a", "b"]);

    expect(calls.map((call) => call.url.href)).toEqual([
      "http://backend:8000/api/charges/",
      "http://backend:8000/api/charges/?page=2",
      "http://backend:8000/api/charges/",
      "http://backend:8000/api/charges",
      "http://backend:8000/api/a/b/",
    ]);
  });
});

describe("BFF request body against a real HTTP backend (RN-PLT-16)", () => {
  it("test_RN_PLT_16_bff_forwards_content_length_and_body_intact", async () => {
    const backend = await startBackend();
    vi.stubEnv("BACKEND_INTERNAL_URL", backend.origin);
    const body = JSON.stringify({ amount: "10.00", note: "café" });
    const length = String(Buffer.byteLength(body));

    const response = await proxyToBackend(
      new Request(`${BFF}/api/charges/`, {
        method: "POST",
        body,
        headers: { "content-type": "application/json", "content-length": length },
      }),
      ["charges"],
    );

    expect(response.status).toBe(200);
    expect(backend.received).toHaveLength(1);
    const [received] = backend.received;
    expect(received!.url).toBe("/api/charges/");
    // Without content-length undici would send `Transfer-Encoding: chunked`.
    expect(received!.headers["content-length"]).toBe(length);
    expect(received!.headers["transfer-encoding"]).toBeUndefined();
    expect(received!.body).toBe(body);
  });
});

describe("BFF upstream errors (RF-PLT-06)", () => {
  it("test_RF_PLT_06_bff_upstream_down_returns_502_problem", async () => {
    // A port nobody listens on any more.
    const backend = await startBackend();
    await backend.close();
    vi.stubEnv("BACKEND_INTERNAL_URL", backend.origin);
    const down = await proxyToBackend(
      new Request(`${BFF}/api/x`, { headers: { "x-request-id": VALID } }),
      ["x"],
    );
    await expectProblem(down, 502, "bff.upstream_unavailable");
    expect(down.headers.get("x-request-id")).toBe(VALID);

    // Any fetch failure maps to the same problem.
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
    mockFetch(async () => {
      throw new TypeError("fetch failed");
    });
    await expectProblem(
      await proxyToBackend(new Request(`${BFF}/api/x`), ["x"]),
      502,
      "bff.upstream_unavailable",
    );

    // Missing or invalid BACKEND_INTERNAL_URL: 502 without echoing the value (C-06).
    for (const value of ["", "not a url sentinel-value", "ftp://sentinel-value:21"]) {
      vi.stubEnv("BACKEND_INTERNAL_URL", value);
      const text = await expectProblem(
        await proxyToBackend(new Request(`${BFF}/api/x`), ["x"]),
        502,
        "bff.upstream_unavailable",
      );
      expect(text).not.toContain("sentinel-value");
      expect(text).not.toContain("BACKEND_INTERNAL_URL");
    }
  });

  it("test_RF_PLT_06_bff_timeout_returns_504_problem", async () => {
    const realTimeout = AbortSignal.timeout.bind(AbortSignal);
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout").mockImplementation(() => realTimeout(50));
    const backend = await startBackend(() => {
      // Never answers.
    });
    vi.stubEnv("BACKEND_INTERNAL_URL", backend.origin);

    const response = await proxyToBackend(new Request(`${BFF}/api/slow`), ["slow"]);

    expect(timeoutSpy).toHaveBeenCalledWith(UPSTREAM_TIMEOUT_MS);
    expect(UPSTREAM_TIMEOUT_MS).toBe(30_000);
    await expectProblem(response, 504, "bff.upstream_timeout");
    expect(backend.received).toHaveLength(1);
  });

  it("test_RF_PLT_06_bff_aborts_upstream_when_browser_disconnects", async () => {
    let upstreamSignal: AbortSignal | undefined;
    mockFetch(
      (init) =>
        new Promise<Response>((_resolve, reject) => {
          upstreamSignal = init.signal ?? undefined;
          init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
        }),
    );
    const browser = new AbortController();

    const pending = proxyToBackend(new Request(`${BFF}/api/x`, { signal: browser.signal }), ["x"]);
    await vi.waitFor(() => expect(upstreamSignal).toBeDefined());
    expect(upstreamSignal!.aborted).toBe(false);
    browser.abort();

    await expectProblem(await pending, 502, "bff.upstream_unavailable");
    expect(upstreamSignal!.aborted).toBe(true);
  });
});

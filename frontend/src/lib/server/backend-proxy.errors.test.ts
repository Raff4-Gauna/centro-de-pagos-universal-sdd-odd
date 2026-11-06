// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { UPSTREAM_TIMEOUT_MS, proxyToBackend } from "./backend-proxy";
import {
  BFF,
  VALID,
  expectProblem,
  installBffTestHooks,
  mockFetch,
  startBackend,
} from "./backend-proxy.test-helpers";

// `server-only` throws outside the react-server condition; the guard is checked in
// backend-proxy.test.ts (test_RN_PLT_16_backend_url_read_at_runtime_server_only).
vi.mock("server-only", () => ({}));

installBffTestHooks();

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

describe("BFF scheme header against a real HTTP backend (RF-PLT-06)", () => {
  it("test_RF_PLT_06_bff_forwarded_proto_reaches_the_backend_as_one_https_value", async () => {
    const backend = await startBackend();
    vi.stubEnv("BACKEND_INTERNAL_URL", backend.origin);

    await proxyToBackend(
      new Request(`${BFF}/api/__smoke__`, { headers: { "x-forwarded-proto": "http" } }),
      ["__smoke__"],
    );

    // On the wire, not on the mock: Django only trusts the first value of a list.
    expect(backend.received).toHaveLength(1);
    expect(backend.received[0]!.headers["x-forwarded-proto"]).toBe("https");
  });
});

describe("BFF request without a usable length (RN-PLT-16)", () => {
  it("test_RN_PLT_16_bff_body_without_content_length_returns_411_problem", async () => {
    const calls = mockFetch();
    const chunked = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"a":1}'));
        controller.close();
      },
    });

    for (const request of [
      new Request(`${BFF}/api/charges/`, {
        method: "POST",
        body: '{"a":1}',
        headers: { "transfer-encoding": "chunked" },
      }),
      new Request(`${BFF}/api/charges/`, {
        method: "PUT",
        body: chunked,
        duplex: "half",
        headers: { "transfer-encoding": "chunked" },
      } as RequestInit & { duplex: "half" }),
      new Request(`${BFF}/api/charges/`, {
        method: "PATCH",
        body: "x",
        headers: { "content-length": "1, 1" },
      }),
    ]) {
      const response = await proxyToBackend(request, ["charges"]);
      await expectProblem(response, 411, "bff.length_required");
    }
    expect(calls).toHaveLength(0);

    // Next hands a bodyless DELETE over with an empty `body` stream: with neither content-length
    // nor transfer-encoding there is no body (RFC 9112 6.3), so it is forwarded without one.
    // Precondition: the second case really carries a (empty) body stream, as Next's does.
    expect(new Request(`${BFF}/x`, { method: "DELETE", body: "" }).body).not.toBeNull();
    for (const init of [{ method: "DELETE" }, { method: "DELETE", body: "" }]) {
      const response = await proxyToBackend(new Request(`${BFF}/api/charges/1/`, init), [
        "charges",
        "1",
      ]);
      expect(response.status).toBe(200);
    }
    expect(calls).toHaveLength(2);
    for (const call of calls) {
      expect(call.init.body).toBeUndefined();
      expect(new Headers(call.init.headers).has("content-length")).toBe(false);
    }
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
    await expectProblem(down, 502, "bff.upstream_unavailable", { reason: "network" });
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
      { reason: "network" },
    );

    // Missing or invalid BACKEND_INTERNAL_URL: 502 without echoing the value (C-06).
    for (const value of ["", "not a url sentinel-value", "ftp://sentinel-value:21"]) {
      vi.stubEnv("BACKEND_INTERNAL_URL", value);
      const text = await expectProblem(
        await proxyToBackend(new Request(`${BFF}/api/x`), ["x"]),
        502,
        "bff.upstream_unavailable",
        { reason: "config" },
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
    await expectProblem(response, 504, "bff.upstream_timeout", { reason: undefined });
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

    // Nobody is waiting for this answer: logged as info, not as an upstream error.
    await expectProblem(await pending, 502, "bff.upstream_unavailable", {
      reason: "client_abort",
      level: "info",
    });
    expect(upstreamSignal!.aborted).toBe(true);
  });
});

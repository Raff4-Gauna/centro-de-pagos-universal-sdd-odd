// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { isSafeBackendTarget, proxyToBackend } from "./backend-proxy";
import {
  BFF,
  VALID,
  expectProblem,
  installBffTestHooks,
  mockFetch,
} from "./backend-proxy.test-helpers";

// `server-only` throws outside the react-server condition; the guard is checked in
// backend-proxy.test.ts (test_RN_PLT_16_backend_url_read_at_runtime_server_only).
vi.mock("server-only", () => ({}));

installBffTestHooks();

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
      ["a\uD800b"], // lone surrogate: encodeURIComponent would throw
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
      // A literal `%` (Next already decoded `%25`) is kept: a later decoding round that fails
      // cannot become a dot segment or a separator, and the output is re-encoded anyway.
      [["a%b"], "http://backend:8000/api/a%25b"],
      [["100%"], "http://backend:8000/api/100%25"],
      [["%zz", "50%2"], "http://backend:8000/api/%25zz/50%252"],
    ];

    for (const [segments] of cases) {
      const response = await proxyToBackend(new Request(`${BFF}/api/whatever`), segments);
      expect(response.status).toBe(200);
    }
    expect(calls.map((call) => call.url.href)).toEqual(cases.map(([, href]) => href));
  });

  it("test_RN_PLT_16_bff_rejects_malformed_encoding_in_the_raw_path", async () => {
    // The first decoding round is the raw path the browser sent (Next decodes it into segments);
    // only there is malformed percent-encoding rejected.
    const calls = mockFetch();
    await expectProblem(
      await proxyToBackend(new Request(`${BFF}/api/%zz`), ["%zz"]),
      400,
      "bff.bad_path",
    );
    await proxyToBackend(new Request(`${BFF}/api/a%25b`), ["a%b"]);
    expect(calls.map((call) => call.url.pathname)).toEqual(["/api/a%25b"]);
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

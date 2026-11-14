// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

import { clientIpFrom, clientIpOf } from "./client-ip";
import { callDjangoBff } from "./django";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const BFF = "http://localhost:3000";
const BINDING = "A".repeat(43);
const REQUEST_ID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";

function forwardedFor(value: string | string[]): Headers {
  const headers = new Headers();
  for (const item of Array.isArray(value) ? value : [value]) {
    headers.append("x-forwarded-for", item);
  }
  return headers;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("client IP in the BFF (AC-IDA-37, RN-IDA-15, design.md §7.6)", () => {
  it("test_AC_IDA_37_ten_clients_behind_one_bff_get_ten_ips", async () => {
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
    vi.stubEnv("HUB_BFF_CREDENTIAL", "test-only-bff-credential");
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "1");
    const sent: (string | null)[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      sent.push(new Headers(init?.headers).get("x-hub-client-ip"));
      return Response.json({ authorization_url: "https://accounts.example/auth" });
    });

    for (let n = 1; n <= 10; n += 1) {
      // Every browser lies the same way on the left; the edge proxy appends the real address.
      const request = new Request(`${BFF}/api/auth/google/start`, {
        headers: { "x-forwarded-for": `198.51.100.1, 203.0.113.${n}` },
      });
      await callDjangoBff({
        path: "/api/auth/bff/login/start/",
        body: { login_binding: BINDING },
        requestId: REQUEST_ID,
        clientIp: clientIpOf(request),
      });
    }
    // One quota per client, not one for the whole BFF.
    expect(sent).toEqual(Array.from({ length: 10 }, (_, i) => `203.0.113.${i + 1}`));
  });

  it("test_AC_IDA_37_counts_trusted_hops_from_the_right", () => {
    const chain = forwardedFor("192.0.2.66, 203.0.113.7, 10.0.0.2, 10.0.0.1");
    expect(clientIpFrom(chain, 1)).toBe("10.0.0.1");
    expect(clientIpFrom(chain, 3)).toBe("203.0.113.7");
    expect(clientIpFrom(chain, 4)).toBe("192.0.2.66");
    // Repeated headers count as one list, in order.
    expect(clientIpFrom(forwardedFor(["192.0.2.66", "203.0.113.7"]), 1)).toBe("203.0.113.7");
    expect(clientIpFrom(forwardedFor("  2001:db8::7 "), 1)).toBe("2001:db8::7");
  });

  it("test_AC_IDA_37_browser_header_is_never_trusted", () => {
    // No trusted proxy: X-Forwarded-For is entirely the browser's.
    expect(clientIpFrom(forwardedFor("203.0.113.7"), 0)).toBeNull();
    // Fewer entries than hops: someone reached the BFF past the proxy.
    expect(clientIpFrom(forwardedFor("203.0.113.7"), 2)).toBeNull();
    expect(clientIpFrom(new Headers(), 1)).toBeNull();
    for (const bad of [
      "unknown",
      "",
      "203.0.113.7:443",
      "[2001:db8::7]",
      "203.0.113.256",
      "a\tb",
    ]) {
      expect(clientIpFrom(forwardedFor(`192.0.2.66, ${bad}`), 1), bad).toBeNull();
    }
    for (const hops of [-1, 1.5, Number.NaN]) {
      expect(clientIpFrom(forwardedFor("203.0.113.7"), hops)).toBeNull();
    }
  });

  it("test_AC_IDA_37_hops_come_from_the_environment", () => {
    const request = new Request(BFF, { headers: { "x-forwarded-for": "203.0.113.7, 10.0.0.1" } });
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "");
    expect(clientIpOf(request)).toBeNull();
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "2");
    expect(clientIpOf(request)).toBe("203.0.113.7");
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "one");
    expect(() => clientIpOf(request)).toThrow(/^HUB_TRUSTED_PROXY_HOPS must be an integer/);
  });
});

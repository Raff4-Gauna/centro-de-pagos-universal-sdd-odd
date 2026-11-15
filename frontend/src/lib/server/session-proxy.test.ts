// @vitest-environment node
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { GET, POST } from "@/app/api/[...path]/route";

import { COOKIE_NAMES } from "./cookies";
import { proxyWithSession } from "./session-proxy";
import {
  ACCESS,
  CSRF,
  ORGANIZATION,
  REFRESH,
  TOKENS,
  browserRequest,
  fakeDjango,
  installSessionProxyHooks,
  logLines,
  segmentsOf,
} from "./session-proxy.test-helpers";

// `server-only` throws outside the react-server condition; the guard is asserted below.
vi.mock("server-only", () => ({}));

installSessionProxyHooks();

const SESSION = {
  [COOKIE_NAMES.access]: ACCESS,
  [COOKIE_NAMES.refresh]: REFRESH,
  [COOKIE_NAMES.csrf]: CSRF,
};

function proxy(request: Request): Promise<Response> {
  return proxyWithSession(request, segmentsOf(request.url));
}

describe("session proxy: what reaches Django (AC-IDA-18, design.md §4.4, §6.3)", () => {
  it("test_AC_IDA_18_access_cookie_becomes_bearer_and_browser_credentials_never_travel", async () => {
    const django = fakeDjango(() => Response.json({ ok: true }));

    const response = await proxy(
      browserRequest("/api/me", {
        cookies: SESSION,
        headers: {
          authorization: "Bearer from-the-browser",
          "x-hub-bff-credential": "forged",
          "x-hub-client-ip": "198.51.100.1",
          "x-organization-id": ORGANIZATION,
        },
      }),
    );

    expect(response.status).toBe(200);
    const [call] = django.calls;
    expect(django.calls).toHaveLength(1);
    expect(call!.path).toBe("/api/me");
    expect(call!.headers.authorization).toBe(`Bearer ${ACCESS}`);
    expect(call!.headers["x-organization-id"]).toBe(ORGANIZATION);
    expect(call!.headers).not.toHaveProperty("cookie");
    for (const name of Object.keys(call!.headers)) {
      expect(name.startsWith("x-hub-"), name).toBe(false);
    }
    // Nothing changed in the session: no cookie is written.
    expect(response.headers.getSetCookie()).toEqual([]);
  });

  it("test_AC_IDA_18_without_session_cookies_the_request_goes_anonymous", async () => {
    const django = fakeDjango(() => Response.json({ ok: true }));

    await proxy(browserRequest("/api/health-like", { headers: { authorization: "Bearer x" } }));

    expect(django.calls).toHaveLength(1);
    expect(django.calls[0]!.headers).not.toHaveProperty("authorization");
  });

  it("test_AC_IDA_18_organization_header_that_is_not_a_uuid_is_dropped", async () => {
    const django = fakeDjango(() => Response.json({ ok: true }));

    for (const value of ["not-a-uuid", `${ORGANIZATION}, ${ORGANIZATION}`, "../x"]) {
      await proxy(
        browserRequest("/api/me", { cookies: SESSION, headers: { "x-organization-id": value } }),
      );
    }

    expect(django.calls).toHaveLength(3);
    for (const call of django.calls) {
      expect(call.headers).not.toHaveProperty("x-organization-id");
    }
  });

  it("test_AC_IDA_18_bff_only_routes_are_not_found_through_the_proxy", async () => {
    const django = fakeDjango(() => Response.json({ ok: true }));
    const denied = [
      ["auth", "bff", "refresh", ""],
      ["auth", "bff", "login", "complete"],
      ["auth", "bff"],
      ["auth", "google", "start"],
      ["AUTH", "Bff", "logout"],
      ["auth", "%62ff", "refresh"],
      ["auth", "%2567oogle", "callback"],
    ];

    for (const segments of denied) {
      const response = await proxyWithSession(
        browserRequest(`/api/${segments.join("/")}`, { method: "POST", cookies: SESSION }),
        segments,
      );
      expect(response.status, segments.join("/")).toBe(404);
      expect(response.headers.get("content-type")).toBe("application/problem+json");
      const body = (await response.json()) as Record<string, unknown>;
      expect(body.code).toBe("not_found");
      expect(response.headers.getSetCookie()).toEqual([]);
    }
    // Django never hears of them: not even the refresh a missing access cookie would trigger.
    expect(django.calls).toEqual([]);
    // Other auth routes do go through (the session endpoints of design.md §6.2).
    await proxy(browserRequest("/api/auth/sessions", { cookies: SESSION }));
    expect(django.calls).toHaveLength(1);
  });

  it("test_AC_IDA_19_mutation_without_csrf_is_refused_before_django", async () => {
    const django = fakeDjango(() => Response.json({ ok: true }));
    const refused = [
      browserRequest("/api/auth/sessions/revoke-others/", {
        method: "POST",
        cookies: SESSION,
        headers: { "x-csrf-token": "d".repeat(43) },
      }),
      browserRequest("/api/charges/", {
        method: "POST",
        cookies: SESSION,
        headers: { origin: "https://evil.example" },
      }),
    ];

    for (const request of refused) {
      const response = await proxy(request);
      expect(response.status).toBe(403);
      expect(((await response.json()) as { code: string }).code).toBe("bff.csrf_failed");
    }
    expect(django.calls).toEqual([]);

    // With Origin and the double-submit token it goes through, with its body.
    await proxy(
      browserRequest("/api/charges/", { method: "POST", cookies: SESSION, body: '{"a":1}' }),
    );
    expect(django.calls).toHaveLength(1);
    expect(django.calls[0]!.body).toBe('{"a":1}');
    expect(django.calls[0]!.headers).not.toHaveProperty("x-csrf-token");
  });

  it("test_AC_IDA_18_early_refusals_log_one_line_without_tokens", async () => {
    fakeDjango(() => Response.json({ ok: true }));

    await proxyWithSession(
      browserRequest("/api/auth/bff/refresh/", { method: "POST", cookies: SESSION }),
      ["auth", "bff", "refresh", ""],
    );

    const lines = logLines();
    expect(lines).toHaveLength(1);
    expect(JSON.parse(lines[0]!)).toMatchObject({
      event: "bff.request",
      route: "/api/[...path]",
      status: 404,
      code: "not_found",
    });
    for (const token of TOKENS) {
      expect(lines[0]).not.toContain(token);
    }
    expect(lines[0]).not.toContain("bff/refresh");
  });

  it("test_AC_IDA_18_route_handler_goes_through_the_session_proxy", async () => {
    const django = fakeDjango(() => Response.json({ ok: true }));
    const context = { params: Promise.resolve({ path: ["me"] }) };

    await GET(browserRequest("/api/me", { cookies: SESSION }), context);
    const denied = await POST(
      browserRequest("/api/auth/bff/logout", { method: "POST", cookies: SESSION }),
      { params: Promise.resolve({ path: ["auth", "bff", "logout"] }) },
    );

    expect(django.calls).toHaveLength(1);
    expect(django.calls[0]!.headers.authorization).toBe(`Bearer ${ACCESS}`);
    expect(denied.status).toBe(404);

    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "session-proxy.ts"), "utf8");
    const firstStatement = source.split("\n").find((line) => line && !line.startsWith("//"));
    expect(firstStatement).toBe('import "server-only";');
    expect(source).not.toContain("NEXT_PUBLIC_");
  });
});

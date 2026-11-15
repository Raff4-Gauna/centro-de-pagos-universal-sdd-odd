// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as route from "./route";

const { PUT, dynamic, runtime } = route;

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const APP = "https://app.example";
const CSRF = "c".repeat(43);
const ORG = "0b7f5b6e-1d2c-4f3a-9b8e-7c6d5e4f3a2b";
const SESSION_COOKIES = `__Host-cpu_rt=rt1.c2lk.refresh; __Host-cpu_csrf=${CSRF}`;
const CSRF_HEADERS = { origin: APP, "x-csrf-token": CSRF, "content-type": "application/json" };

function put(
  body: string | null,
  headers: Record<string, string> = CSRF_HEADERS,
  cookie: string | null = SESSION_COOKIES,
): Promise<Response> {
  const all = cookie === null ? headers : { ...headers, cookie };
  return PUT(
    new Request(`${APP}/api/session/active-organization`, { method: "PUT", headers: all, body }),
  );
}

function json(value: unknown): string {
  return JSON.stringify(value);
}

type Problem = { code: string; status: number; request_id: string; errors?: unknown[] };

beforeEach(() => {
  vi.stubEnv("HUB_APP_ORIGIN", APP);
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Django must not be called"));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("PUT /api/session/active-organization", () => {
  it("runs on Node.js and is never cached", () => {
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
    expect(Object.keys(route).sort()).toEqual(["PUT", "dynamic", "runtime"]);
  });

  it("test_Q_119_cookie_is_format_only", async () => {
    // Any well-formed id is kept, member or not: the cookie is a preference and Django
    // revalidates the membership on every request (SPEC-02). The BFF asks nobody.
    const response = await put(json({ organization_id: ORG }));

    expect(response.status).toBe(204);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
    expect(response.headers.getSetCookie()).toEqual([
      `__Host-cpu_org=${ORG}; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Lax`,
    ]);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("test_Q_119_an_uppercase_uuid_is_stored_in_canonical_form", async () => {
    const response = await put(json({ organization_id: ORG.toUpperCase() }));

    expect(response.status).toBe(204);
    expect(response.headers.getSetCookie()[0]).toContain(`__Host-cpu_org=${ORG};`);
  });

  it("test_Q_119_null_clears_the_preference", async () => {
    const response = await put(json({ organization_id: null }));

    expect(response.status).toBe(204);
    expect(response.headers.getSetCookie()).toEqual([
      "__Host-cpu_org=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax",
    ]);
  });

  it.each([
    ["missing", {}, "required"],
    ["a number", { organization_id: 42 }, "invalid"],
    ["not a uuid", { organization_id: "acme" }, "invalid"],
    ["a uuid in braces", { organization_id: `{${ORG}}` }, "invalid"],
    ["a uuid without hyphens", { organization_id: ORG.replaceAll("-", "") }, "invalid"],
    ["a uuid with spaces", { organization_id: ` ${ORG}` }, "invalid"],
    [
      "a uuid with a cookie attribute",
      { organization_id: `${ORG}; Domain=evil.example` },
      "invalid",
    ],
  ])("test_Q_119_an_organization_id_%s_is_a_validation_error", async (_case, body, code) => {
    const response = await put(json(body));

    expect(response.status).toBe(400);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.getSetCookie()).toEqual([]);
    const problem = (await response.json()) as Problem;
    expect(problem).toMatchObject({ code: "validation_error", status: 400 });
    expect(problem.request_id).toBe(response.headers.get("x-request-id"));
    expect(problem.errors).toEqual([
      { field: "organization_id", code, message: expect.any(String) as string },
    ]);
  });

  it.each([
    ["no body", null],
    ["malformed JSON", "{organization_id:"],
    ["an array", json([ORG])],
    ["a string", json(ORG)],
    ["an oversized body", json({ organization_id: ORG, padding: "x".repeat(4096) })],
  ])("test_Q_119_%s_is_a_parse_error", async (_case, body) => {
    const response = await put(body);

    expect(response.status).toBe(400);
    expect(((await response.json()) as Problem).code).toBe("parse_error");
    expect(response.headers.getSetCookie()).toEqual([]);
  });

  it.each([
    ["without the CSRF header", { origin: APP }, SESSION_COOKIES],
    ["with another CSRF token", { origin: APP, "x-csrf-token": "d".repeat(43) }, SESSION_COOKIES],
    [
      "from another origin",
      { origin: "https://evil.example", "x-csrf-token": CSRF },
      SESSION_COOKIES,
    ],
    ["without a CSRF cookie", { origin: APP, "x-csrf-token": CSRF }, null],
  ])("test_AC_IDA_19_a_change_%s_is_refused", async (_case, headers, cookie) => {
    const response = await put(json({ organization_id: ORG }), headers, cookie);

    expect(response.status).toBe(403);
    expect(((await response.json()) as Problem).code).toBe("bff.csrf_failed");
    expect(response.headers.getSetCookie()).toEqual([]);
  });
});

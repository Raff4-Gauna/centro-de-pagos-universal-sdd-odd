// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { COOKIE_NAMES, type BffCookie } from "./cookies";
import {
  type RefreshedSession,
  cookiesAfterRefresh,
  cookiesAfterRejectedRefresh,
  pendingRefreshCount,
  refreshSession,
} from "./refresh";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const REQUEST_ID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";
const OTHER_REQUEST_ID = "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f";
const REFRESH = "rt1.0b6c2c1e-4d3a-4e5f-9a8b-7c6d5e4f3a2b.secret-part_A1";
const SUCCESSOR = "rt1.0b6c2c1e-4d3a-4e5f-9a8b-7c6d5e4f3a2b.successor_B2";
const ACCESS = "test-only.access-token.sentinel";
const CSRF = "c".repeat(43);
const CLIENT = { clientIp: "203.0.113.7", clientUserAgent: "Mozilla/5.0" };

type Call = { url: URL; init: RequestInit };

function rotated(refreshToken: string | null = SUCCESSOR): Response {
  return Response.json({
    access_token: ACCESS,
    access_expires_in: 900,
    refresh_token: refreshToken,
    session_expires_in: 604_800,
  });
}

function problem(status: number, code: string, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ status, code }), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });
}

// Django behind a gate: every call waits until `release` answers it, so the test decides what is
// concurrent.
function gatedDjango() {
  const calls: Call[] = [];
  const waiting: Array<(response: Response) => void> = [];
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    calls.push({ url: new URL(String(input)), init: init ?? {} });
    return new Promise<Response>((resolve) => waiting.push(resolve));
  });
  return {
    calls,
    release(response: Response) {
      const next = waiting.shift();
      if (next === undefined) {
        throw new Error("no call is waiting");
      }
      next(response);
    },
  };
}

function djangoAnswers(response: () => Response | Promise<Response>) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push({ url: new URL(String(input)), init: init ?? {} });
    return response();
  });
  return calls;
}

function refresh(token = REFRESH, client: object = CLIENT, requestId = REQUEST_ID) {
  return refreshSession({ refreshToken: token, requestId, ...client });
}

function byName(cookies: BffCookie[]): Record<string, BffCookie> {
  return Object.fromEntries(cookies.map((cookie) => [cookie.name, cookie]));
}

beforeEach(() => {
  vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
  vi.stubEnv("HUB_BFF_CREDENTIAL", "test-only-bff-credential-sentinel");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Refresh coalescing in the BFF (RN-IDA-10, AC-IDA-28, design.md §4.5)", () => {
  it("test_AC_IDA_28_concurrent_refreshes_share_one_call_to_django", async () => {
    const django = gatedDjango();
    const tabs = [refresh(), refresh(REFRESH, CLIENT, OTHER_REQUEST_ID), refresh()];
    expect(pendingRefreshCount()).toBe(1);

    django.release(rotated());
    const outcomes = await Promise.all(tabs);

    // One rotation, not three: Django never sees the token twice, so no reuse is possible.
    expect(django.calls).toHaveLength(1);
    const [call] = django.calls;
    expect(call!.url.href).toBe("http://backend:8000/api/auth/bff/refresh/");
    expect(JSON.parse(String(call!.init.body))).toEqual({ refresh_token: REFRESH });
    const sent = new Headers(call!.init.headers);
    expect(sent.get("x-request-id")).toBe(REQUEST_ID);
    expect(sent.get("x-hub-client-ip")).toBe("203.0.113.7");
    for (const outcome of outcomes) {
      expect(outcome).toEqual({
        kind: "refreshed",
        session: {
          accessToken: ACCESS,
          accessExpiresIn: 900,
          refreshToken: SUCCESSOR,
          sessionExpiresIn: 604_800,
        },
      });
    }
    expect(pendingRefreshCount()).toBe(0);
  });

  it("test_AC_IDA_28_a_refresh_after_the_first_settled_calls_django_again", async () => {
    const calls = djangoAnswers(() => rotated(null));
    await refresh();
    await refresh();
    // Sequential refreshes are not coalesced: Django's grace window answers the second one.
    expect(calls).toHaveLength(2);
  });

  it("test_AC_IDA_28_different_tokens_or_clients_are_not_coalesced", async () => {
    const django = gatedDjango();
    const pending = [
      refresh(),
      refresh(SUCCESSOR),
      refresh(REFRESH, { clientIp: "198.51.100.9", clientUserAgent: "Mozilla/5.0" }),
      refresh(REFRESH, { clientIp: "203.0.113.7", clientUserAgent: "curl/8.0" }),
    ];
    expect(django.calls).toHaveLength(4);
    expect(pendingRefreshCount()).toBe(4);
    for (let index = 0; index < 4; index += 1) {
      django.release(rotated());
    }
    await Promise.all(pending);
    expect(pendingRefreshCount()).toBe(0);
  });

  it("test_AC_IDA_28_grace_answer_keeps_the_refresh_cookie", async () => {
    djangoAnswers(() => rotated(null));
    const outcome = await refresh();

    expect(outcome).toMatchObject({ kind: "refreshed", session: { refreshToken: null } });
    const session = (outcome as { session: RefreshedSession }).session;
    const cookies = cookiesAfterRefresh(session, CSRF);
    // Only the access cookie: rewriting `rt` would overwrite the successor the browser holds.
    expect(cookies.map((cookie) => cookie.name)).toEqual([COOKIE_NAMES.access]);
    expect(cookies[0]).toMatchObject({ value: ACCESS, maxAge: 840, httpOnly: true });
  });

  it("test_AC_IDA_28_rotation_writes_the_successor_and_renews_csrf", () => {
    const session: RefreshedSession = {
      accessToken: ACCESS,
      accessExpiresIn: 900,
      refreshToken: SUCCESSOR,
      sessionExpiresIn: 604_800,
    };
    const cookies = byName(cookiesAfterRefresh(session, CSRF));

    expect(Object.keys(cookies)).toEqual([
      COOKIE_NAMES.access,
      COOKIE_NAMES.refresh,
      COOKIE_NAMES.csrf,
    ]);
    expect(cookies[COOKIE_NAMES.refresh]).toMatchObject({ value: SUCCESSOR, maxAge: 604_800 });
    // Same CSRF value (open tabs keep working), lifetime moved with the session.
    expect(cookies[COOKIE_NAMES.csrf]).toMatchObject({
      value: CSRF,
      maxAge: 604_800,
      httpOnly: false,
    });
  });

  it("test_AC_IDA_28_rotation_mints_csrf_when_the_browser_has_none_valid", () => {
    const session: RefreshedSession = {
      accessToken: ACCESS,
      accessExpiresIn: 900,
      refreshToken: SUCCESSOR,
      sessionExpiresIn: 3_600,
    };
    for (const current of [null, "", "short", `${CSRF};x=1`]) {
      const csrf = byName(cookiesAfterRefresh(session, current))[COOKIE_NAMES.csrf]!;
      expect(csrf.value).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(csrf.value).not.toBe(current);
      expect(csrf.maxAge).toBe(3_600);
    }
  });

  it("test_AC_IDA_28_revoked_or_invalid_refresh_is_rejected_for_every_waiting_tab", async () => {
    const django = gatedDjango();
    const tabs = [refresh(), refresh()];
    django.release(problem(401, "session_revoked"));
    expect(await Promise.all(tabs)).toEqual([
      { kind: "rejected", code: "session_revoked" },
      { kind: "rejected", code: "session_revoked" },
    ]);

    djangoAnswers(() => problem(401, "token_invalid"));
    expect(await refresh()).toEqual({ kind: "rejected", code: "token_invalid" });
  });

  it("test_AC_IDA_28_any_other_401_still_ends_the_session", async () => {
    djangoAnswers(() => new Response("not json", { status: 401 }));
    expect(await refresh()).toEqual({ kind: "rejected", code: "session_revoked" });
  });

  it("test_AC_IDA_28_rejected_refresh_clears_access_refresh_and_csrf", () => {
    const cookies = cookiesAfterRejectedRefresh();
    expect(cookies.map((cookie) => cookie.name)).toEqual([
      COOKIE_NAMES.access,
      COOKIE_NAMES.refresh,
      COOKIE_NAMES.csrf,
    ]);
    for (const cookie of cookies) {
      expect(cookie).toMatchObject({ value: "", maxAge: 0 });
    }
  });

  it("test_AC_IDA_28_malformed_token_is_rejected_without_calling_django", async () => {
    const calls = djangoAnswers(() => rotated());
    for (const token of ["", "a b", "x".repeat(257), "rt1;evil=1", "rt1.é"]) {
      expect(await refresh(token)).toEqual({ kind: "rejected", code: "token_invalid" });
    }
    expect(calls).toHaveLength(0);
  });

  it("test_AC_IDA_28_rate_limit_keeps_the_cookies_and_passes_retry_after", async () => {
    djangoAnswers(() => problem(429, "rate_limited", { "retry-after": "12" }));
    expect(await refresh()).toEqual({ kind: "rate_limited", retryAfter: "12" });

    djangoAnswers(() => problem(429, "rate_limited", { "retry-after": "Wed, 21 Oct 2026" }));
    expect(await refresh()).toEqual({ kind: "rate_limited", retryAfter: null });
  });

  it("test_AC_IDA_28_upstream_failures_are_unavailable_not_rejected", async () => {
    djangoAnswers(() => problem(503, "internal_error"));
    expect(await refresh()).toEqual({ kind: "unavailable", reason: "upstream_error" });

    djangoAnswers(() => problem(404, "not_found"));
    expect(await refresh()).toEqual({ kind: "unavailable", reason: "upstream_error" });

    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    expect(await refresh()).toEqual({ kind: "unavailable", reason: "network" });

    vi.stubEnv("HUB_BFF_CREDENTIAL", "");
    expect(await refresh()).toEqual({ kind: "unavailable", reason: "config" });
  });

  it("test_AC_IDA_28_unexpected_200_body_is_a_bad_response", async () => {
    const bodies: unknown[] = [
      { access_token: ACCESS, access_expires_in: 900, session_expires_in: 60 },
      { access_token: "", access_expires_in: 900, refresh_token: null, session_expires_in: 60 },
      {
        access_token: ACCESS,
        access_expires_in: "900",
        refresh_token: null,
        session_expires_in: 1,
      },
      { access_token: ACCESS, access_expires_in: 900, refresh_token: "a;b", session_expires_in: 1 },
      { access_token: ACCESS, access_expires_in: 900, refresh_token: null, session_expires_in: -1 },
      [],
    ];
    for (const body of bodies) {
      djangoAnswers(() => Response.json(body));
      expect(await refresh()).toEqual({ kind: "unavailable", reason: "bad_response" });
    }
    djangoAnswers(() => new Response("<html>", { status: 200 }));
    expect(await refresh()).toEqual({ kind: "unavailable", reason: "bad_response" });
  });

  it("test_AC_IDA_28_a_throwing_upstream_still_settles_every_waiting_tab", async () => {
    // A response that blows up when read: the shared promise must settle, not reject.
    const broken = {
      get status(): number {
        throw new Error(REFRESH);
      },
    } as unknown as Response;
    djangoAnswers(() => broken);
    expect(await Promise.all([refresh(), refresh()])).toEqual([
      { kind: "unavailable", reason: "upstream_error" },
      { kind: "unavailable", reason: "upstream_error" },
    ]);
    expect(pendingRefreshCount()).toBe(0);
  });

  it("test_AC_IDA_28_outcomes_never_carry_the_presented_token", async () => {
    const outcomes = [];
    for (const response of [rotated(null), problem(401, "token_invalid"), problem(500, "x")]) {
      djangoAnswers(() => response);
      outcomes.push(await refresh());
    }
    expect(JSON.stringify(outcomes)).not.toContain(REFRESH);
  });
});

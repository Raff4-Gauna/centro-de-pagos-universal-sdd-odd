// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { COOKIE_NAMES } from "./cookies";
import { proxyWithSession } from "./session-proxy";
import {
  ACCESS,
  CSRF,
  NEW_ACCESS,
  REFRESH,
  SUCCESSOR,
  TOKENS,
  browserRequest,
  fakeDjango,
  installSessionProxyHooks,
  logLines,
  problem,
  rotated,
  segmentsOf,
  setCookies,
} from "./session-proxy.test-helpers";

vi.mock("server-only", () => ({}));

installSessionProxyHooks();

const SESSION = {
  [COOKIE_NAMES.access]: ACCESS,
  [COOKIE_NAMES.refresh]: REFRESH,
  [COOKIE_NAMES.csrf]: CSRF,
};
const WITHOUT_ACCESS = { [COOKIE_NAMES.refresh]: REFRESH, [COOKIE_NAMES.csrf]: CSRF };

function proxy(request: Request): Promise<Response> {
  return proxyWithSession(request, segmentsOf(request.url));
}

// Django rejects the old access token and accepts the new one.
function expiresOld(call: { headers: Record<string, string> }): Response {
  return call.headers.authorization === `Bearer ${NEW_ACCESS}`
    ? Response.json({ ok: true })
    : problem(401, "token_expired");
}

function expectSessionCleared(response: Response): void {
  const cookies = setCookies(response);
  for (const name of [COOKIE_NAMES.access, COOKIE_NAMES.refresh, COOKIE_NAMES.csrf]) {
    expect(cookies[name], name).toMatch(/=; Max-Age=0; Path=\/; Secure/);
  }
}

async function expectNoTokenLeak(response: Response): Promise<void> {
  const text = await response.clone().text();
  for (const token of TOKENS) {
    expect(text).not.toContain(token);
    expect(logLines().join("")).not.toContain(token);
  }
}

describe("session proxy: transparent refresh (AC-IDA-28, design.md §4.4, §4.5)", () => {
  it("test_AC_IDA_28_token_expired_refreshes_once_and_retries_once", async () => {
    const django = fakeDjango(expiresOld);

    const response = await proxy(browserRequest("/api/me", { cookies: SESSION }));

    expect(response.status).toBe(200);
    expect(django.refreshCalls()).toHaveLength(1);
    expect(JSON.parse(django.refreshCalls()[0]!.body)).toEqual({ refresh_token: REFRESH });
    expect(django.apiCalls().map((call) => call.headers.authorization)).toEqual([
      `Bearer ${ACCESS}`,
      `Bearer ${NEW_ACCESS}`,
    ]);
    const cookies = setCookies(response);
    expect(cookies[COOKIE_NAMES.access]).toContain(`=${NEW_ACCESS}; Max-Age=840;`);
    expect(cookies[COOKIE_NAMES.access]).toContain("HttpOnly");
    expect(cookies[COOKIE_NAMES.refresh]).toContain(`=${SUCCESSOR};`);
    expect(cookies[COOKIE_NAMES.refresh]).toContain("HttpOnly");
    // The CSRF token keeps its value; only its lifetime follows the session.
    expect(cookies[COOKIE_NAMES.csrf]).toContain(`=${CSRF}; Max-Age=604800;`);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expectNoTokenLeak(response);
  });

  it("test_AC_IDA_28_a_mutation_is_retried_with_the_same_body", async () => {
    const django = fakeDjango(expiresOld);
    const body = '{"amount":"10.00"}';

    const response = await proxy(
      browserRequest("/api/charges/", { method: "POST", cookies: SESSION, body }),
    );

    expect(response.status).toBe(200);
    expect(django.apiCalls().map((call) => call.body)).toEqual([body, body]);
    expect(django.apiCalls()[1]!.headers["content-length"]).toBe(String(body.length));
  });

  it("test_AC_IDA_28_retry_happens_once_even_if_django_still_says_expired", async () => {
    const django = fakeDjango(() => problem(401, "token_expired"));

    const response = await proxy(browserRequest("/api/me", { cookies: SESSION }));

    expect(response.status).toBe(401);
    expect(django.refreshCalls()).toHaveLength(1);
    expect(django.apiCalls()).toHaveLength(2);
    expectSessionCleared(response);
  });

  it("test_AC_IDA_28_missing_access_cookie_refreshes_before_calling_django", async () => {
    const django = fakeDjango(() => Response.json({ ok: true }));

    const response = await proxy(browserRequest("/api/me", { cookies: WITHOUT_ACCESS }));

    expect(response.status).toBe(200);
    expect(django.calls.map((call) => call.path)).toEqual(["/api/auth/bff/refresh/", "/api/me"]);
    expect(django.apiCalls()[0]!.headers.authorization).toBe(`Bearer ${NEW_ACCESS}`);
    // The refresh carries the browser's IP (one trusted hop) with the BFF credential.
    expect(django.refreshCalls()[0]!.headers["x-hub-client-ip"]).toBe("203.0.113.7");
    expect(setCookies(response)[COOKIE_NAMES.access]).toContain(`=${NEW_ACCESS};`);
  });

  it("test_AC_IDA_28_two_tabs_share_one_refresh_and_both_keep_working", async () => {
    let answer: (response: Response) => void = () => undefined;
    const gate = new Promise<Response>((resolve) => {
      answer = resolve;
    });
    const django = fakeDjango(
      () => Response.json({ ok: true }),
      () => gate,
    );

    const tabs = Promise.all([
      proxy(browserRequest("/api/me", { cookies: WITHOUT_ACCESS })),
      proxy(browserRequest("/api/auth/sessions", { cookies: WITHOUT_ACCESS })),
    ]);
    await vi.waitFor(() => expect(django.refreshCalls()).toHaveLength(1));
    answer(rotated());
    const responses = await tabs;

    expect(django.refreshCalls()).toHaveLength(1);
    expect(responses.map((response) => response.status)).toEqual([200, 200]);
    for (const response of responses) {
      expect(setCookies(response)[COOKIE_NAMES.refresh]).toContain(`=${SUCCESSOR};`);
    }
  });

  it("test_AC_IDA_28_grace_window_only_rewrites_the_access_cookie", async () => {
    fakeDjango(expiresOld, () => rotated(null));

    const response = await proxy(browserRequest("/api/me", { cookies: SESSION }));

    expect(response.status).toBe(200);
    expect(Object.keys(setCookies(response))).toEqual([COOKIE_NAMES.access]);
  });
});

describe("session proxy: the session cannot go on (AC-IDA-26, spec §14)", () => {
  it("test_AC_IDA_26_session_revoked_is_not_retried_and_clears_the_cookies", async () => {
    const django = fakeDjango(() => problem(401, "session_revoked"));

    const response = await proxy(browserRequest("/api/me", { cookies: SESSION }));

    expect(response.status).toBe(401);
    expect(((await response.clone().json()) as { code: string }).code).toBe("session_revoked");
    expect(django.refreshCalls()).toEqual([]);
    expect(django.apiCalls()).toHaveLength(1);
    expectSessionCleared(response);
    // The organization preference survives; only logout clears it.
    expect(setCookies(response)).not.toHaveProperty(COOKIE_NAMES.organization);
  });

  it("test_AC_IDA_26_rejected_refresh_answers_session_revoked_and_clears_cookies", async () => {
    for (const code of ["session_revoked", "token_invalid"]) {
      const django = fakeDjango(expiresOld, () => problem(401, code));

      const response = await proxy(browserRequest("/api/me", { cookies: SESSION }));

      expect(response.status, code).toBe(401);
      expect(response.headers.get("content-type")).toBe("application/problem+json");
      expect(((await response.clone().json()) as { code: string }).code).toBe("session_revoked");
      expect(django.apiCalls(), code).toHaveLength(1);
      expectSessionCleared(response);
      await expectNoTokenLeak(response);
      vi.restoreAllMocks();
      installStdoutAgain();
    }
  });

  it("test_AC_IDA_26_rejected_preemptive_refresh_never_calls_the_api", async () => {
    const django = fakeDjango(
      () => Response.json({ ok: true }),
      () => problem(401, "session_revoked"),
    );

    const response = await proxy(browserRequest("/api/me", { cookies: WITHOUT_ACCESS }));

    expect(response.status).toBe(401);
    expect(django.apiCalls()).toEqual([]);
    expectSessionCleared(response);
  });

  it("test_AC_IDA_26_refresh_throttled_or_unavailable_keeps_the_cookies", async () => {
    fakeDjango(expiresOld, () => problem(429, "rate_limited", { "retry-after": "12" }));
    const throttled = await proxy(browserRequest("/api/me", { cookies: SESSION }));
    expect(throttled.status).toBe(429);
    expect(throttled.headers.get("retry-after")).toBe("12");
    expect(((await throttled.json()) as { code: string }).code).toBe("rate_limited");
    expect(throttled.headers.getSetCookie()).toEqual([]);

    vi.restoreAllMocks();
    installStdoutAgain();
    fakeDjango(expiresOld, () => new Response(null, { status: 503 }));
    const unavailable = await proxy(browserRequest("/api/me", { cookies: SESSION }));
    expect(unavailable.status).toBe(502);
    expect(((await unavailable.json()) as { code: string }).code).toBe("bff.upstream_unavailable");
    expect(unavailable.headers.getSetCookie()).toEqual([]);
  });

  it("test_AC_IDA_26_unauthenticated_without_refresh_cookie_passes_through", async () => {
    const django = fakeDjango(() => problem(401, "unauthenticated"));

    const response = await proxy(browserRequest("/api/me"));

    expect(response.status).toBe(401);
    expect(django.refreshCalls()).toEqual([]);
    expect(response.headers.getSetCookie()).toEqual([]);
  });
});

// `vi.restoreAllMocks` inside a test also drops the stdout capture of the hooks.
function installStdoutAgain(): void {
  logLines().length = 0;
  vi.spyOn(process.stdout, "write").mockImplementation((chunk: string | Uint8Array) => {
    logLines().push(String(chunk));
    return true;
  });
}

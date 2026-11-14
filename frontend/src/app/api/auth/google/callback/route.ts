// GET /api/auth/google/callback?code&state[&error] (RF-IDA-02, design.md §4.1, §6.3): Google sends
// the browser back here. This handler relays `state`, `code` and `error` to Django with the binding
// of `__Host-cpu_login`, the client IP and the User-Agent; Django runs every rule of the callback
// (design.md §4.2) and, if the person may enter, opens the session and returns its tokens.
//
// Success: the tokens go into the `HttpOnly` cookies `__Host-cpu_at` and `__Host-cpu_rt`, a fresh
// CSRF token into `__Host-cpu_csrf` (rotated on every login), `__Host-cpu_login` is cleared and the
// browser is sent to the `.href` of `returnUrl(return_path)`: never the raw path, which could
// resolve to another host (AC-IDA-19). No token ever travels in a body or a URL (AC-IDA-18). A
// previous session in the same browser ends with `logout(reason=superseded)`, best effort.
//
// Failure: `__Host-cpu_login` is cleared too and the browser goes to `/login?error=<code>`, a code
// of the allowlist; neither Google's `error`, the `state` nor the `code` reach that URL.
import {
  COOKIE_NAMES,
  type BffCookie,
  accessCookie,
  clearedCookie,
  csrfCookie,
  randomCookieToken,
  refreshCookie,
} from "@/lib/server/cookies";
import { clientIpOf } from "@/lib/server/client-ip";
import { callDjangoBff } from "@/lib/server/django";
import {
  type LoginErrorCode,
  appOriginOrNull,
  isLoginBinding,
  loginErrorCode,
  loginErrorRedirect,
  loginRedirect,
  problemCodeOf,
  readCookie,
} from "@/lib/server/login-flow";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/server/request-id";
import { returnUrl } from "@/lib/server/return-path";
import type { components } from "@/types/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type LoginSession = components["schemas"]["LoginCompleteResponse"];

// Google's `error` is relayed reduced to what Django tells apart (design.md §4.2, step 3): the
// person cancelled, or anything else. The raw value never leaves the BFF.
const ACCESS_DENIED = "access_denied";
const OTHER_PROVIDER_ERROR = "provider_error";

function providerError(raw: string | null): string | null {
  if (raw === null || raw === "") {
    return null;
  }
  return raw === ACCESS_DENIED ? ACCESS_DENIED : OTHER_PROVIDER_ERROR;
}

function isSeconds(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isToken(value: unknown): value is string {
  return typeof value === "string" && value !== "";
}

async function sessionOf(response: Response): Promise<LoginSession | null> {
  try {
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null) {
      return null;
    }
    const session = body as Partial<Record<keyof LoginSession, unknown>>;
    const valid =
      isToken(session.access_token) &&
      isToken(session.refresh_token) &&
      isSeconds(session.access_expires_in) &&
      isSeconds(session.session_expires_in);
    return valid ? (body as LoginSession) : null;
  } catch {
    return null;
  }
}

function sessionCookies(session: LoginSession): BffCookie[] | null {
  try {
    return [
      accessCookie(session.access_token, session.access_expires_in),
      refreshCookie(session.refresh_token, session.session_expires_in),
      csrfCookie(randomCookieToken(), session.session_expires_in),
      clearedCookie(COOKIE_NAMES.login),
    ];
  } catch {
    // A token that cannot be a cookie value; the error names the cookie, never the value.
    return null;
  }
}

// The session this browser had before ends, so a login over another one leaves no orphan behind
// (design.md §6.3). Best effort: whatever happens, the new session stands.
async function endPreviousSession(request: Request, session: LoginSession, requestId: string) {
  const previousRefresh = readCookie(request, COOKIE_NAMES.refresh);
  if (previousRefresh === null || previousRefresh === "") {
    return;
  }
  if (previousRefresh === session.refresh_token) {
    return;
  }
  const previousAccess = readCookie(request, COOKIE_NAMES.access);
  const outcome = await callDjangoBff({
    path: "/api/auth/bff/logout/",
    body: {
      refresh_token: previousRefresh,
      access_token: previousAccess === "" ? null : previousAccess,
      reason: "superseded",
    },
    requestId,
  });
  if (outcome.kind === "response") {
    await outcome.response.body?.cancel();
  }
}

export async function GET(request: Request): Promise<Response> {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const appOrigin = appOriginOrNull();
  const clearLogin = clearedCookie(COOKIE_NAMES.login);
  const fail = (code: LoginErrorCode) =>
    loginErrorRedirect(code, appOrigin, requestId, [clearLogin]);
  // Checked before Django opens a session that could not be landed in.
  if (appOrigin === null) {
    return fail("internal_error");
  }

  // Without the binding no attempt can be consumed: the callback was not started by this browser.
  const binding = readCookie(request, COOKIE_NAMES.login);
  if (!isLoginBinding(binding)) {
    return fail("google_auth_failed");
  }

  let clientIp: string | null;
  try {
    clientIp = clientIpOf(request);
  } catch {
    return fail("internal_error");
  }

  const params = new URL(request.url).searchParams;
  const outcome = await callDjangoBff({
    path: "/api/auth/bff/login/complete/",
    body: {
      // An empty state matches no attempt: Django answers google_auth_failed (and audits it).
      state: params.get("state") ?? "",
      login_binding: binding,
      code: params.get("code"),
      error: providerError(params.get("error")),
    },
    requestId,
    clientIp,
    clientUserAgent: request.headers.get("user-agent"),
    signal: request.signal,
  });
  if (outcome.kind === "unavailable") {
    return fail("internal_error");
  }

  const { response } = outcome;
  if (response.status !== 200) {
    const code = await problemCodeOf(response);
    // An over-long `state` or `code` in the URL: what Google sent is not valid.
    return fail(code === "validation_error" ? "google_auth_failed" : loginErrorCode(code));
  }
  const session = await sessionOf(response);
  const cookies = session === null ? null : sessionCookies(session);
  if (session === null || cookies === null) {
    return fail("internal_error");
  }

  await endPreviousSession(request, session, requestId);
  return loginRedirect(returnUrl(session.return_path, appOrigin).href, requestId, cookies);
}

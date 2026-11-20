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

// A lock of an invitation's organization not taken in time (SPEC-02 Q-230) is Django's
// `503 organization_busy`. The attempt and Google's `code` are spent by then, so the same callback
// cannot be sent again: the person starts the login over, with Q-127's "Reintentar" (Q-231). Its
// `Retry-After` is not relayed.
const ORGANIZATION_BUSY = "organization_busy";

function failureCode(code: string | null): LoginErrorCode {
  // An over-long `state` or `code` in the URL: what Google sent is not valid.
  if (code === "validation_error") {
    return "google_auth_failed";
  }
  return code === ORGANIZATION_BUSY ? "google_unavailable" : loginErrorCode(code);
}

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

type LoginReply = Partial<Record<keyof LoginSession, unknown>>;

async function replyOf(response: Response): Promise<LoginReply | null> {
  try {
    const body: unknown = await response.json();
    return typeof body === "object" && body !== null ? (body as LoginReply) : null;
  } catch {
    return null;
  }
}

function sessionOf(reply: LoginReply | null): LoginSession | null {
  if (reply === null) {
    return null;
  }
  const valid =
    isToken(reply.access_token) &&
    isToken(reply.refresh_token) &&
    isSeconds(reply.access_expires_in) &&
    isSeconds(reply.session_expires_in);
  return valid ? (reply as LoginSession) : null;
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

// Ends a session best effort (ADR-0004 §13): whatever Django answers, or if it does not, the
// login goes on. No browser signal: the logout must not be cut short if the person leaves.
async function supersede(refreshToken: string, accessToken: string | null, requestId: string) {
  const outcome = await callDjangoBff({
    path: "/api/auth/bff/logout/",
    body: { refresh_token: refreshToken, access_token: accessToken, reason: "superseded" },
    requestId,
  });
  if (outcome.kind === "response") {
    await outcome.response.body?.cancel();
  }
}

// The session this browser had before ends, so a login over another one leaves no orphan behind
// (design.md §6.3). An absent or repeated `__Host-cpu_rt` names none.
async function endPreviousSession(request: Request, session: LoginSession, requestId: string) {
  const previousRefresh = readCookie(request, COOKIE_NAMES.refresh);
  if (previousRefresh === null || previousRefresh === "") {
    return;
  }
  if (previousRefresh === session.refresh_token) {
    return;
  }
  const previousAccess = readCookie(request, COOKIE_NAMES.access);
  await supersede(previousRefresh, previousAccess === "" ? null : previousAccess, requestId);
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

  // Without a usable binding (absent, repeated or of another shape) no attempt can be consumed, but
  // the callback still goes to Django with `login_binding: null`: it answers google_auth_failed and
  // audits the rejection, under its `login_complete_ip` throttle (design.md §4.2 step 2, Q-128).
  const cookie = readCookie(request, COOKIE_NAMES.login);
  const binding = isLoginBinding(cookie) ? cookie : null;

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
      // An empty state, or no binding, matches no attempt: Django answers google_auth_failed (and
      // audits it).
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
    return fail(failureCode(await problemCodeOf(response)));
  }
  const reply = await replyOf(response);
  const session = sessionOf(reply);
  const cookies = session === null ? null : sessionCookies(session);
  if (session === null || cookies === null) {
    // Django opened a session this browser cannot hold: if its refresh token is readable, the
    // same logout ends it (ADR-0004 §13); if not, it expires by inactivity.
    if (reply !== null && isToken(reply.refresh_token)) {
      await supersede(reply.refresh_token, null, requestId);
    }
    return fail("internal_error");
  }

  await endPreviousSession(request, session, requestId);
  return loginRedirect(returnUrl(session.return_path, appOrigin).href, requestId, cookies);
}

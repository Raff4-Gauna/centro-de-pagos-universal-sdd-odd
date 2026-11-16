// POST /api/auth/logout (RF-IDA-05, RN-IDA-14, AC-IDA-17, AC-IDA-35, design.md §4.6, §6.3): ends the
// session of this browser. The handler relays the refresh token and the access token of the
// cookies to Django's `auth/bff/logout`, which revokes the session they name (the access token
// counts even if it already expired) and answers `204` whether there was one or not.
//
// The browser always gets a bodiless `204` that clears `__Host-cpu_at`, `__Host-cpu_rt`,
// `__Host-cpu_csrf` and `__Host-cpu_org`, **whatever Django answered**: DRF can refuse before the
// view (`400 parse_error`, `415`), and a `5XX`, a timeout or a network failure must not leave the
// browser holding the session (T-IDA-25, note of T-IDA-16). Logging out twice, or without a session,
// is the same `204`.
//
// CSRF (RN-IDA-13, design.md §7.2): with a session cookie, both checks (Origin and double submit);
// a refusal is `403 bff.csrf_failed`, no cookie is touched and Django never hears of it, so another
// site cannot end the session. Without one there is no CSRF cookie to compare: the Origin check
// alone keeps another site from clearing the preference cookie.
import {
  COOKIE_NAMES,
  type BffCookie,
  type CookieName,
  clearedCookie,
  serializeCookie,
} from "@/lib/server/cookies";
import { checkCsrfToken, checkOrigin, csrfFailure, requestCookieValues } from "@/lib/server/csrf";
import { callDjangoBff } from "@/lib/server/django";
import { readCookie } from "@/lib/server/login-flow";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/server/request-id";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SESSION_COOKIES: readonly CookieName[] = [COOKIE_NAMES.access, COOKIE_NAMES.refresh];

// What a logout clears (design.md §7.1, column "Se borra"). `__Host-cpu_login` is not part of a
// session: a login in progress in another tab goes on.
const CLEARED_ON_LOGOUT: readonly CookieName[] = [
  COOKIE_NAMES.access,
  COOKIE_NAMES.refresh,
  COOKIE_NAMES.csrf,
  COOKIE_NAMES.organization,
];

// Any session cookie with a value, even a repeated one: an ambiguous session still needs the
// full CSRF check, it is not treated as no session.
function hasSessionCookie(request: Request): boolean {
  return SESSION_COOKIES.some((name) =>
    requestCookieValues(request.headers, name).some((value) => value !== ""),
  );
}

// The token of one cookie, or null if it is absent, empty or repeated (it names no session then).
function tokenOf(request: Request, name: CookieName): string | null {
  const value = readCookie(request, name);
  return value === null || value === "" ? null : value;
}

// Best effort (ADR-0004 §13): the outcome is not looked at, the cookies are cleared anyway. No
// browser signal: the revocation must not be cut short if the person closes the tab.
async function revoke(refreshToken: string | null, accessToken: string | null, requestId: string) {
  const outcome = await callDjangoBff({
    path: "/api/auth/bff/logout/",
    body: { refresh_token: refreshToken, access_token: accessToken, reason: "logout" },
    requestId,
  });
  if (outcome.kind === "response") {
    // Discarding the reply must not fail the logout: the cookies are cleared whatever happens.
    await outcome.response.body?.cancel().catch(() => {});
  }
}

function loggedOut(requestId: string): Response {
  const headers = new Headers({ "cache-control": "no-store", [REQUEST_ID_HEADER]: requestId });
  const cookies: BffCookie[] = CLEARED_ON_LOGOUT.map(clearedCookie);
  for (const cookie of cookies) {
    headers.append("set-cookie", serializeCookie(cookie));
  }
  return new Response(null, { status: 204, headers });
}

export async function POST(request: Request): Promise<Response> {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const withSession = hasSessionCookie(request);

  const origin = checkOrigin(request.headers);
  const check = origin.ok && withSession ? checkCsrfToken(request.headers) : origin;
  const refused = csrfFailure(check, requestId);
  if (refused !== null) {
    return refused;
  }

  if (withSession) {
    const refreshToken = tokenOf(request, COOKIE_NAMES.refresh);
    const accessToken = tokenOf(request, COOKIE_NAMES.access);
    if (refreshToken !== null || accessToken !== null) {
      await revoke(refreshToken, accessToken, requestId);
    }
  }
  return loggedOut(requestId);
}

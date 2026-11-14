import "server-only";

import { createHash } from "node:crypto";

import {
  COOKIE_NAMES,
  type BffCookie,
  accessCookie,
  clearedCookie,
  csrfCookie,
  randomCookieToken,
  refreshCookie,
} from "./cookies";
import { type DjangoUnavailableReason, callDjangoBff } from "./django";

// Refresh of the session from the BFF (RF-IDA-04, RN-IDA-10, AC-IDA-28, design.md §4.5,
// ADR-0004 §3). Django rotates the refresh token and tolerates concurrent refreshes with a 30 s
// grace window; on top of that, each BFF instance coalesces them: requests that arrive with the
// same refresh token while a refresh is in flight share that one call to Django, so two tabs of
// one browser landing on the same instance rotate once, not twice.
//
// The tokens never reach a log line, an error message or the browser's body (C-06, RN-IDA-12):
// they only travel to Django in the request body and back to the browser in HttpOnly cookies.
const REFRESH_PATH = "/api/auth/bff/refresh/" as const;

// A refresh token is `rt1.<sid>.<secret>` (~90 B). Anything longer is refused here instead of
// being sent: Django would only answer `token_invalid`.
const MAX_REFRESH_TOKEN_LENGTH = 256;
// What a token issued by Django looks like (JWT in base64url with dots; `rt1.<uuid>.<base64url>`):
// a value outside it is not written into a cookie.
const TOKEN_CHARACTERS = /^[A-Za-z0-9._~+/=-]+$/;
// The CSRF cookie the BFF itself mints: 32 random bytes in base64url.
const CSRF_TOKEN_SHAPE = /^[A-Za-z0-9_-]{43}$/;
const RETRY_AFTER_SHAPE = /^\d{1,6}$/;

export type RefreshedSession = Readonly<{
  accessToken: string;
  accessExpiresIn: number;
  // `null`: Django answered within the grace window. The browser already holds the successor in
  // `__Host-cpu_rt`, from the response of the request that rotated; it must not be touched.
  refreshToken: string | null;
  sessionExpiresIn: number;
}>;

export type RefreshRejection = "token_invalid" | "session_revoked";

export type RefreshUnavailableReason = DjangoUnavailableReason | "upstream_error" | "bad_response";

export type RefreshOutcome =
  | { kind: "refreshed"; session: RefreshedSession }
  // The session cannot go on: the caller clears the cookies (`cookiesAfterRejectedRefresh`).
  | { kind: "rejected"; code: RefreshRejection }
  | { kind: "rate_limited"; retryAfter: string | null }
  // Nothing is known about the session: the cookies stay as they are. `reason` is for the logs.
  | { kind: "unavailable"; reason: RefreshUnavailableReason };

export type RefreshCall = Readonly<{
  refreshToken: string;
  requestId: string;
  clientIp?: string | null;
  clientUserAgent?: string | null;
}>;

const REJECTED_INVALID: RefreshOutcome = Object.freeze({ kind: "rejected", code: "token_invalid" });

// In-flight refreshes of this instance, by `coalescingKey`. An entry lives only while its call to
// Django is pending, so the map never grows past the refreshes running at that moment.
const inFlight = new Map<string, Promise<RefreshOutcome>>();

// The hash of the token, never the token. The client IP and User-Agent are part of the key: tabs
// of one browser share them, while someone else holding a stolen copy of the token, racing the
// legitimate refresh, does not get the rotated pair handed over; Django's grace and reuse rules
// decide that request on their own.
function coalescingKey(call: RefreshCall): string {
  return createHash("sha256")
    .update(call.refreshToken, "utf8")
    .update("\0")
    .update(call.clientIp ?? "", "utf8")
    .update("\0")
    .update(call.clientUserAgent ?? "", "utf8")
    .digest("hex");
}

function isLifetime(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isToken(value: unknown): value is string {
  return typeof value === "string" && TOKEN_CHARACTERS.test(value);
}

function parseSession(body: unknown): RefreshedSession | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const fields = body as Record<string, unknown>;
  const refreshToken = fields.refresh_token;
  if (
    !isToken(fields.access_token) ||
    !isLifetime(fields.access_expires_in) ||
    !isLifetime(fields.session_expires_in) ||
    !(refreshToken === null || isToken(refreshToken))
  ) {
    return null;
  }
  return Object.freeze({
    accessToken: fields.access_token,
    accessExpiresIn: fields.access_expires_in,
    refreshToken,
    sessionExpiresIn: fields.session_expires_in,
  });
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function discardBody(response: Response): Promise<void> {
  try {
    await response.body?.cancel();
  } catch {
    // Nothing to do: the body is not needed.
  }
}

// Every 401 of the refresh means the cookies are worthless (design.md §6.1); only the code that
// goes back to the caller differs.
async function rejection(response: Response): Promise<RefreshOutcome> {
  const body = await readJson(response);
  const code = typeof body === "object" && body !== null && "code" in body ? body.code : undefined;
  return { kind: "rejected", code: code === "token_invalid" ? "token_invalid" : "session_revoked" };
}

async function interpret(response: Response): Promise<RefreshOutcome> {
  if (response.status === 200) {
    const session = parseSession(await readJson(response));
    return session === null
      ? { kind: "unavailable", reason: "bad_response" }
      : { kind: "refreshed", session };
  }
  if (response.status === 401) {
    return rejection(response);
  }
  await discardBody(response);
  if (response.status === 429) {
    const retryAfter = response.headers.get("retry-after");
    return {
      kind: "rate_limited",
      retryAfter: retryAfter !== null && RETRY_AFTER_SHAPE.test(retryAfter) ? retryAfter : null,
    };
  }
  // 404 (credential refused), 5xx or anything else the contract does not describe.
  return { kind: "unavailable", reason: "upstream_error" };
}

async function callRefresh(call: RefreshCall): Promise<RefreshOutcome> {
  try {
    // No browser signal: the call is shared, and one tab closing must not cancel the refresh of
    // the others. The timeout of django.ts still bounds it.
    const outcome = await callDjangoBff({
      path: REFRESH_PATH,
      body: { refresh_token: call.refreshToken },
      requestId: call.requestId,
      clientIp: call.clientIp ?? null,
    });
    if (outcome.kind === "unavailable") {
      return { kind: "unavailable", reason: outcome.reason };
    }
    return await interpret(outcome.response);
  } catch {
    // Never rejects: whoever awaits the shared promise gets an outcome. The error is dropped, not
    // logged: it could carry the request.
    return { kind: "unavailable", reason: "upstream_error" };
  }
}

// Refreshes the session of `refreshToken` (the value of `__Host-cpu_rt`). Concurrent calls with
// the same token, client IP and User-Agent get the very same outcome from a single call to Django;
// the first caller's request id is the one Django sees.
export function refreshSession(call: RefreshCall): Promise<RefreshOutcome> {
  const token = call.refreshToken;
  if (token === "" || token.length > MAX_REFRESH_TOKEN_LENGTH || !isToken(token)) {
    return Promise.resolve(REJECTED_INVALID);
  }
  const key = coalescingKey(call);
  const pending = inFlight.get(key);
  if (pending !== undefined) {
    return pending;
  }
  const refresh = callRefresh(call).finally(() => {
    inFlight.delete(key);
  });
  inFlight.set(key, refresh);
  return refresh;
}

// Refreshes in flight in this instance (for tests and diagnostics; no token is exposed).
export function pendingRefreshCount(): number {
  return inFlight.size;
}

// Cookies for the browser after a successful refresh. The access cookie always changes. With a
// rotation, the refresh cookie gets the successor and the CSRF cookie the same new lifetime (the
// current value is kept, or a new one minted if the browser has none that the BFF could have
// written). Within the grace window (`refreshToken === null`) neither is touched: writing the old
// token back would overwrite the successor the browser already holds (design.md §4.5).
export function cookiesAfterRefresh(
  session: RefreshedSession,
  currentCsrfToken: string | null,
): BffCookie[] {
  const cookies = [accessCookie(session.accessToken, session.accessExpiresIn)];
  if (session.refreshToken !== null) {
    const csrf =
      currentCsrfToken !== null && CSRF_TOKEN_SHAPE.test(currentCsrfToken)
        ? currentCsrfToken
        : randomCookieToken();
    cookies.push(
      refreshCookie(session.refreshToken, session.sessionExpiresIn),
      csrfCookie(csrf, session.sessionExpiresIn),
    );
  }
  return cookies;
}

// A rejected refresh ends the session in this browser: access, refresh and CSRF cookies are
// cleared (design.md §7.1). The organization preference stays; only logout clears it.
export function cookiesAfterRejectedRefresh(): BffCookie[] {
  return [COOKIE_NAMES.access, COOKIE_NAMES.refresh, COOKIE_NAMES.csrf].map(clearedCookie);
}

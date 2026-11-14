import "server-only";

import { type BffCookie, type CookieName, serializeCookie } from "./cookies";
import { requestCookieValues } from "./csrf";
import { getAppOrigin } from "./env";
import { REQUEST_ID_HEADER } from "./request-id";

// What the two login route handlers share (app/api/auth/google/{start,callback}, design.md §6.3):
// the cookies they read, the `/login?error=` codes they may send the browser to and the shape of
// their redirects. Every response is a bodiless `302` with `Cache-Control: no-store` and
// `Referrer-Policy: no-referrer` (design.md §7.5): the callback URL carries Google's `code` and
// `state`, and neither must reach a cache or the `Referer` of the next page.

export const LOGIN_PAGE_PATH = "/login";

// The only codes `/login?error=` ever gets (design.md §6.3); anything else becomes the generic
// `internal_error`, so neither a detail nor a value from the request ever reaches the URL.
export const LOGIN_ERROR_CODES = [
  "login_cancelled",
  "google_auth_failed",
  "google_unavailable",
  "email_not_verified",
  "not_invited",
  "user_inactive",
  "identity_conflict",
  "rate_limited",
  "login_disabled",
  "session_expired",
  "internal_error",
] as const;

export type LoginErrorCode = (typeof LOGIN_ERROR_CODES)[number];

const ALLOWED_CODES: ReadonlySet<string> = new Set(LOGIN_ERROR_CODES);

export function loginErrorCode(raw: unknown): LoginErrorCode {
  return typeof raw === "string" && ALLOWED_CODES.has(raw)
    ? (raw as LoginErrorCode)
    : "internal_error";
}

// 32 random bytes in base64url (cookies.ts `randomCookieToken`), as Django checks it
// (`is_login_binding`): a cookie of any other shape is ignored, never sent.
const LOGIN_BINDING = /^[A-Za-z0-9_-]{43}$/;

export function isLoginBinding(value: string | null): value is string {
  return value !== null && LOGIN_BINDING.test(value);
}

// The value of one cookie of the request, or null when it is absent or repeated: like the CSRF
// check (csrf.ts), an ambiguous cookie is not picked from, it counts as missing.
export function readCookie(request: Request, name: CookieName): string | null {
  const values = requestCookieValues(request.headers, name);
  return values.length === 1 ? values[0]! : null;
}

// The `code` of a problem+json from Django, filtered by the allowlist. The body is read only for
// that field: it is never logged nor passed on.
export async function problemCodeOf(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "code" in body) {
      return typeof body.code === "string" ? body.code : null;
    }
  } catch {
    // Not JSON: no code.
  }
  return null;
}

export function loginRedirect(
  location: string,
  requestId: string,
  cookies: readonly BffCookie[] = [],
): Response {
  const headers = new Headers({
    location,
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    [REQUEST_ID_HEADER]: requestId,
  });
  for (const cookie of cookies) {
    headers.append("set-cookie", serializeCookie(cookie));
  }
  return new Response(null, { status: 302, headers });
}

// `/login?error=<code>` on the app origin. Without a valid origin (a configuration error), the
// same fixed path as a relative reference: nothing in it comes from the request.
export function loginErrorRedirect(
  code: LoginErrorCode,
  appOrigin: string | null,
  requestId: string,
  cookies: readonly BffCookie[] = [],
): Response {
  const query = new URLSearchParams({ error: code }).toString();
  const path = `${LOGIN_PAGE_PATH}?${query}`;
  const location = appOrigin === null ? path : new URL(path, appOrigin).href;
  return loginRedirect(location, requestId, cookies);
}

// The configured origin, or null if it is missing or malformed (the error names the variable, and
// is not passed on either).
export function appOriginOrNull(): string | null {
  try {
    return getAppOrigin();
  } catch {
    return null;
  }
}

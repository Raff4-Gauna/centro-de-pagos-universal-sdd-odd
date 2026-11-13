import "server-only";

import { randomBytes } from "node:crypto";

// The BFF's cookies (RN-IDA-12, AC-IDA-18, design.md §7.1, ADR-0004). Every one is `Secure`,
// `Path=/` and has no `Domain`, as the `__Host-` prefix demands (the browser refuses it otherwise),
// so no other host or path can set or shadow it. Tokens only travel in `HttpOnly` cookies: the one
// cookie JavaScript may read is the CSRF token, which grants nothing by itself (design.md §7.2).
// `SameSite=Lax`, not `Strict`: the landing after Google's redirect and the links of invitation
// emails are top-level navigations from another site and must arrive with the cookies.
export const COOKIE_NAMES = {
  access: "__Host-cpu_at",
  refresh: "__Host-cpu_rt",
  csrf: "__Host-cpu_csrf",
  login: "__Host-cpu_login",
  organization: "__Host-cpu_org",
} as const;

export type CookieName = (typeof COOKIE_NAMES)[keyof typeof COOKIE_NAMES];

export type BffCookie = Readonly<{
  name: CookieName;
  value: string;
  maxAge: number;
  httpOnly: boolean;
  secure: true;
  path: "/";
  sameSite: "lax";
}>;

// The access cookie dies a minute before the token so the BFF refreshes before Django rejects it.
export const ACCESS_COOKIE_MARGIN_S = 60;
export const LOGIN_COOKIE_MAX_AGE_S = 600;
export const ORGANIZATION_COOKIE_MAX_AGE_S = 30 * 24 * 60 * 60;
// Absolute life of a session (design.md §8.2): no cookie of the session outlives it.
export const SESSION_ABSOLUTE_MAX_AGE_S = 30 * 24 * 60 * 60;

// RFC 6265 cookie-octet: no space, `"`, `,`, `;`, `\`, control or non-ASCII character, so a value
// can neither break the header nor smuggle an attribute.
const COOKIE_OCTETS = /^[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]*$/;

function lifetime(seconds: number): number {
  if (!Number.isSafeInteger(seconds) || seconds < 0) {
    throw new RangeError("invalid cookie lifetime");
  }
  return seconds;
}

function cookie(name: CookieName, value: string, maxAge: number, httpOnly: boolean): BffCookie {
  if (!COOKIE_OCTETS.test(value)) {
    // The value is never part of the message: it may be a token.
    throw new TypeError(`invalid value for cookie ${name}`);
  }
  return {
    name,
    value,
    maxAge: lifetime(maxAge),
    httpOnly,
    secure: true,
    path: "/",
    sameSite: "lax",
  };
}

function sessionLifetime(sessionExpiresIn: number): number {
  return Math.min(lifetime(sessionExpiresIn), SESSION_ABSOLUTE_MAX_AGE_S);
}

export function accessCookie(accessToken: string, accessExpiresIn: number): BffCookie {
  const maxAge = Math.max(lifetime(accessExpiresIn) - ACCESS_COOKIE_MARGIN_S, 0);
  return cookie(COOKIE_NAMES.access, accessToken, maxAge, true);
}

export function refreshCookie(refreshToken: string, sessionExpiresIn: number): BffCookie {
  return cookie(COOKIE_NAMES.refresh, refreshToken, sessionLifetime(sessionExpiresIn), true);
}

// Readable by the api-client, which echoes it in X-CSRF-Token (double submit, RN-IDA-13).
export function csrfCookie(csrfToken: string, sessionExpiresIn: number): BffCookie {
  return cookie(COOKIE_NAMES.csrf, csrfToken, sessionLifetime(sessionExpiresIn), false);
}

export function loginCookie(loginBinding: string): BffCookie {
  return cookie(COOKIE_NAMES.login, loginBinding, LOGIN_COOKIE_MAX_AGE_S, true);
}

// A preference, not an authorization: Django checks the membership on every request (Q-119).
export function organizationCookie(organizationId: string): BffCookie {
  return cookie(COOKIE_NAMES.organization, organizationId, ORGANIZATION_COOKIE_MAX_AGE_S, true);
}

// Deletion: same name and attributes (a `__Host-` cookie is only replaced by one that has them),
// empty value and `Max-Age=0`.
export function clearedCookie(name: CookieName): BffCookie {
  const httpOnly = name !== COOKIE_NAMES.csrf;
  return cookie(name, "", 0, httpOnly);
}

// 32 random bytes in base64url (43 characters): the CSRF token and the login binding.
export function randomCookieToken(): string {
  return randomBytes(32).toString("base64url");
}

// The `Set-Cookie` header value, for `headers.append("set-cookie", …)`.
export function serializeCookie(bffCookie: BffCookie): string {
  const { name, value, maxAge, httpOnly } = cookie(
    bffCookie.name,
    bffCookie.value,
    bffCookie.maxAge,
    bffCookie.httpOnly,
  );
  const attributes = [`${name}=${value}`, `Max-Age=${maxAge}`, "Path=/", "Secure"];
  if (httpOnly) {
    attributes.push("HttpOnly");
  }
  attributes.push("SameSite=Lax");
  return attributes.join("; ");
}

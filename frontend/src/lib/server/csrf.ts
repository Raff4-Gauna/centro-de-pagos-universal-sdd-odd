import "server-only";

import { createHash, timingSafeEqual } from "node:crypto";

import { COOKIE_NAMES } from "./cookies";
import { getAppOrigin } from "./env";
import { bffProblem } from "./problem";

// CSRF protection of the BFF (RN-IDA-13, AC-IDA-19, design.md §7.2, ADR-0004 §6). The session
// travels in cookies, so every request that may change state is checked twice before Django is
// called: (1) where it comes from (`Origin` exactly `HUB_APP_ORIGIN`; without `Origin`,
// `Sec-Fetch-Site: same-origin`; without either, refused) and (2) double submit: `X-CSRF-Token`
// equals the `__Host-cpu_csrf` cookie, compared in constant time. The `__Host-` prefix keeps a
// subdomain from planting that cookie, so no HMAC is added. A failure is `403 bff.csrf_failed`
// and Django never hears of the request. The BFF enables no CORS.
//
// Neither the token nor the cookie is ever part of a message or a log line (C-06): the `reason`
// of a refusal only names which check failed, for the logs.
export const CSRF_HEADER = "x-csrf-token";
export const ORIGIN_HEADER = "origin";
export const FETCH_SITE_HEADER = "sec-fetch-site";

// RFC 9110 §9.2.1. Everything else, including a method the BFF does not know, is checked: an
// unknown method fails closed instead of skipping the protection.
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export type CsrfRefusal =
  "config" | "origin_missing" | "origin_mismatch" | "token_missing" | "token_mismatch";

export type CsrfCheck = { ok: true } | { ok: false; reason: CsrfRefusal };

const PASSED: CsrfCheck = { ok: true };

function refused(reason: CsrfRefusal): CsrfCheck {
  return { ok: false, reason };
}

export function isSafeMethod(method: string): boolean {
  return SAFE_METHODS.has(method.toUpperCase());
}

// Values of the cookie `name` in a `Cookie` header, in order. A repeated name is kept repeated:
// the caller decides (the CSRF check refuses an ambiguous cookie rather than pick one).
export function requestCookieValues(headers: Headers, name: string): string[] {
  const header = headers.get("cookie");
  if (header === null) {
    return [];
  }
  const values: string[] = [];
  for (const pair of header.split(";")) {
    const separator = pair.indexOf("=");
    if (separator !== -1 && pair.slice(0, separator).trim() === name) {
      values.push(pair.slice(separator + 1).trim());
    }
  }
  return values;
}

// (1) Origin. `Origin: null` (sandboxed frame, opaque origin) is a mismatch, not a missing header.
// `Sec-Fetch-Site` is only the fallback for a browser that left `Origin` out; when both are there,
// `Origin` decides.
export function checkOrigin(headers: Headers): CsrfCheck {
  let appOrigin: string;
  try {
    appOrigin = getAppOrigin();
  } catch {
    // Without a configured origin nothing can be compared: refused, never let through.
    return refused("config");
  }
  const origin = headers.get(ORIGIN_HEADER);
  if (origin !== null) {
    return origin === appOrigin ? PASSED : refused("origin_mismatch");
  }
  const fetchSite = headers.get(FETCH_SITE_HEADER);
  if (fetchSite === null) {
    return refused("origin_missing");
  }
  return fetchSite === "same-origin" ? PASSED : refused("origin_mismatch");
}

// Both sides are hashed first so `timingSafeEqual` compares equal lengths and the time spent does
// not depend on how many characters match, nor on the token's length.
function sameSecret(a: string, b: string): boolean {
  const digestA = createHash("sha256").update(a, "utf8").digest();
  const digestB = createHash("sha256").update(b, "utf8").digest();
  return timingSafeEqual(digestA, digestB);
}

// (2) Double submit. An absent or empty header or cookie, or two `__Host-cpu_csrf` cookies, fail.
export function checkCsrfToken(headers: Headers): CsrfCheck {
  const sent = headers.get(CSRF_HEADER);
  const cookies = requestCookieValues(headers, COOKIE_NAMES.csrf);
  if (sent === null || sent === "" || cookies.length !== 1 || cookies[0] === "") {
    return refused("token_missing");
  }
  return sameSecret(sent, cookies[0]!) ? PASSED : refused("token_mismatch");
}

// The whole check for a request: a safe method passes untouched; any other needs both checks.
export function checkCsrf(request: Request): CsrfCheck {
  if (isSafeMethod(request.method)) {
    return PASSED;
  }
  const origin = checkOrigin(request.headers);
  if (!origin.ok) {
    return origin;
  }
  return checkCsrfToken(request.headers);
}

// For a Route Handler: `null` when the request may go on, otherwise the `403 bff.csrf_failed`
// response to return as is, without calling Django.
export function csrfFailure(check: CsrfCheck, requestId: string): Response | null {
  return check.ok ? null : bffProblem("bff.csrf_failed", requestId);
}

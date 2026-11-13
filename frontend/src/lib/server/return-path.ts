import "server-only";

// Where the browser lands after the login (RN-IDA-13, AC-IDA-19): never an open redirect.
//
// Same rule as the backend's `sanitize_return_path` (backend/apps/identity/domain/return_path.py),
// applied twice by the BFF: before sending `return_path` to Django (a value Django would refuse
// with 400, like one holding U+0000, becomes "Inicio" here instead) and again before redirecting
// to what Django hands back. Only an internal path survives: one leading `/`, no `//`, no `\`, no
// control, format, separator (other than the space) or unassigned character, at most 512 code
// points. A hostile value is replaced whole, never repaired.
//
// The value is checked exactly as it arrives: it is NEVER percent-decoded first. The browser does
// not decode a redirect target either, so `/%2F%2Fevil.example` or `/%5Cevil.example` stay paths
// of the app, and decoding here would only open a gap between what is checked and what is used.
// As a last guard the redirect target is resolved against the app origin and must stay on it.
export const DEFAULT_RETURN_PATH = "/";
export const MAX_RETURN_PATH_LENGTH = 512;

// Python's `str.isprintable()` is false for categories C* (Cc, Cf, Cs, Co, Cn) and Z* (Zs, Zl, Zp)
// except the ASCII space, which is taken out before the test. With the `u` flag a lone surrogate
// counts as Cs.
const NOT_PRINTABLE = /[\p{C}\p{Z}]/u;

export function sanitizeReturnPath(raw: unknown): string {
  if (typeof raw !== "string") {
    return DEFAULT_RETURN_PATH;
  }
  // Code points, as Python's len(): an astral character is one, not two UTF-16 units.
  const length = [...raw].length;
  if (length === 0 || length > MAX_RETURN_PATH_LENGTH) {
    return DEFAULT_RETURN_PATH;
  }
  if (!raw.startsWith("/") || raw.startsWith("//")) {
    return DEFAULT_RETURN_PATH;
  }
  // Browsers read "\" as "/" and drop tabs and line breaks: "/\host" and "/<tab>/host" are
  // "//host" to them.
  if (raw.includes("\\") || NOT_PRINTABLE.test(raw.replaceAll(" ", ""))) {
    return DEFAULT_RETURN_PATH;
  }
  return raw;
}

// The absolute URL to redirect to: the sanitized path on `appOrigin`, or "Inicio" if resolving it
// would leave that origin (it cannot after `sanitizeReturnPath`; this keeps it that way).
export function returnUrl(raw: unknown, appOrigin: string): URL {
  const origin = new URL(appOrigin).origin;
  const target = new URL(sanitizeReturnPath(raw), origin);
  return target.origin === origin ? target : new URL(DEFAULT_RETURN_PATH, origin);
}

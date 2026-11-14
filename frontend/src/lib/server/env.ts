import "server-only";

// Server-only configuration of the BFF (RN-PLT-16, Q-050). The backend URL is internal: it is
// read from the server's environment on every call (never frozen into the build, never a public
// client-exposed variable) and error messages never echo the configured value (C-06).
const ALLOWED_PROTOCOLS = new Set(["http:", "https:"]);

export function getBackendInternalUrl(): URL {
  const raw = process.env.BACKEND_INTERNAL_URL;
  if (!raw) {
    throw new Error("BACKEND_INTERNAL_URL is not set");
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("BACKEND_INTERNAL_URL is not a valid URL");
  }
  if (!ALLOWED_PROTOCOLS.has(url.protocol)) {
    throw new Error("BACKEND_INTERNAL_URL is not a valid http(s) URL");
  }
  return url;
}

// Credential the BFF presents to Django's `auth/bff/*` in X-Hub-Bff-Credential (RN-IDA-12,
// ADR-0004 §9). A secret: it is never logged, echoed in an error or sent to the browser (C-06).
// Visible ASCII only: anything else could not travel in a header, and the error `Headers` would
// throw names the offending value.
const CREDENTIAL_CHARACTERS = /^[\x21-\x7e]+$/;

export function getBffCredential(): string {
  const value = process.env.HUB_BFF_CREDENTIAL;
  if (!value) {
    throw new Error("HUB_BFF_CREDENTIAL is not set");
  }
  if (!CREDENTIAL_CHARACTERS.test(value)) {
    throw new Error("HUB_BFF_CREDENTIAL has characters that are not visible ASCII");
  }
  return value;
}

// Origin the browser sees (`https://<app>`), the only one an unsafe request may come from and the
// base every post-login redirect is resolved against (RN-IDA-13, design.md §7.2). Returned
// normalized (`URL.origin`); a value with a path, query, fragment or user info is refused.
export function getAppOrigin(): string {
  const raw = process.env.HUB_APP_ORIGIN;
  if (!raw) {
    throw new Error("HUB_APP_ORIGIN is not set");
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("HUB_APP_ORIGIN is not a valid URL");
  }
  const bare = url.pathname === "/" && !url.search && !url.hash && !url.username && !url.password;
  if (!ALLOWED_PROTOCOLS.has(url.protocol) || !bare || raw.includes("?") || raw.includes("#")) {
    throw new Error("HUB_APP_ORIGIN is not a valid http(s) origin");
  }
  return url.origin;
}

// Proxies in front of the BFF that append to X-Forwarded-For (design.md §7.6). Unset or empty: 0,
// no proxy is trusted and the BFF reports no client IP. Bounded so a typo cannot reach past the
// whole header.
export const MAX_TRUSTED_PROXY_HOPS = 10;

export function getTrustedProxyHops(): number {
  const raw = process.env.HUB_TRUSTED_PROXY_HOPS;
  if (!raw) {
    return 0;
  }
  const hops = /^\d{1,2}$/.test(raw) ? Number(raw) : Number.NaN;
  if (!(hops <= MAX_TRUSTED_PROXY_HOPS)) {
    throw new Error(
      `HUB_TRUSTED_PROXY_HOPS must be an integer from 0 to ${MAX_TRUSTED_PROXY_HOPS}`,
    );
  }
  return hops;
}

import "server-only";

import { isIP } from "node:net";

import { getTrustedProxyHops } from "./env";

// IP of the browser behind the proxies (RN-IDA-15, AC-IDA-37, design.md §7.6, ADR-0004 §9).
//
// Every browser reaches Django through the BFF, so Django alone would see one address and give all
// of them one login quota. The BFF reports the real one in X-Hub-Client-IP, only to `auth/bff/*`
// (django.ts), and Django believes it only next to a valid BFF credential.
//
// Each trusted proxy appends the address it received the connection from to X-Forwarded-For, so
// with N trusted hops the client is the N-th entry from the right; whatever lies further left was
// written by the browser and is never read. 0 hops (no proxy, or none configured), fewer entries
// than hops or an entry that is not a bare IP → `null`: no header is sent and Django falls back to
// the BFF's address (the shared quota), the safe side. Ports and brackets are not stripped: a
// trusted proxy writes bare addresses, and anything else is a misconfiguration to notice.
export const FORWARDED_FOR_HEADER = "x-forwarded-for";

export function clientIpFrom(headers: Headers, trustedHops: number): string | null {
  if (!Number.isSafeInteger(trustedHops) || trustedHops <= 0) {
    return null;
  }
  // Repeated headers arrive joined with ", " (Fetch `Headers.get`), in order.
  const forwardedFor = headers.get(FORWARDED_FOR_HEADER);
  if (forwardedFor === null) {
    return null;
  }
  const entries = forwardedFor.split(",").map((entry) => entry.trim());
  if (entries.length < trustedHops) {
    return null;
  }
  const candidate = entries[entries.length - trustedHops]!;
  return isIP(candidate) === 0 ? null : candidate;
}

// The client IP of an incoming request, with the hops configured in HUB_TRUSTED_PROXY_HOPS.
export function clientIpOf(request: Request): string | null {
  return clientIpFrom(request.headers, getTrustedProxyHops());
}

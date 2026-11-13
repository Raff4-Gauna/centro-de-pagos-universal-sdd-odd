import "server-only";

import type { paths } from "@/types/api";

import { getBackendInternalUrl, getBffCredential } from "./env";
import { REQUEST_ID_HEADER } from "./request-id";
import { sanitizeReturnPath } from "./return-path";

// Client of the BFF for Django's `auth/bff/*` (design.md §6.1, ADR-0004 §9, RN-IDA-12). Only these
// endpoints get the BFF credential, the client IP and the client User-Agent; the catch-all proxy
// (backend-proxy.ts) never sends any of them. The credential is read from the server environment
// on every call and goes nowhere but the X-Hub-Bff-Credential header: never a log line, an error
// message or a response for the browser (C-06).
//
// Paths and bodies come from the generated contract (`specs/_contracts/openapi.yaml`), so only the
// endpoints the backend publishes can be called. The response is returned as Django sent it, for
// the route handler to read; network failures, timeouts and missing configuration become an
// `unavailable` outcome whose `reason` is for the logs only.
export const BFF_CREDENTIAL_HEADER = "x-hub-bff-credential";
export const CLIENT_IP_HEADER = "x-hub-client-ip";
export const CLIENT_UA_HEADER = "x-hub-client-ua";

// Always `https` (Q-065): the internal hop is plain HTTP and `SECURE_SSL_REDIRECT` would answer
// every request with a 301 in prod.
const FORWARDED_PROTO_HEADER = "x-forwarded-proto";
const FORWARDED_PROTO = "https";

// The slowest call, login/complete, exchanges the code with Google (connect 3 s + read 5 s) and may
// fetch its JWKS (5 s): this leaves room for both without hanging a login forever.
export const DJANGO_BFF_TIMEOUT_MS = 15_000;

// Django only keeps a 32-character summary of browser and OS; a longer header is cut, not refused.
const MAX_USER_AGENT_LENGTH = 512;
// Tab, visible ASCII and Latin-1: what a header value can carry (anything else would make `Headers`
// throw), minus every control character.
const NOT_HEADER_SAFE = /[^\t\x20-\x7e\xa0-\xff]/;

type BffPath = Extract<keyof paths, `/api/auth/bff/${string}`>;
type PostOf<P extends BffPath> = paths[P] extends { post: infer O } ? O : never;
export type BffRequestBody<P extends BffPath> =
  PostOf<P> extends { requestBody: { content: { "application/json": infer B } } } ? B : never;

export type DjangoBffCall<P extends BffPath> = Readonly<{
  path: P;
  body: BffRequestBody<P>;
  requestId: string;
  clientIp?: string | null;
  clientUserAgent?: string | null;
  // The browser's request signal: Django's work is abandoned if the browser goes away.
  signal?: AbortSignal;
}>;

export type DjangoUnavailableReason = "config" | "network" | "timeout" | "client_abort";

export type DjangoBffOutcome =
  | { kind: "response"; response: Response }
  | { kind: "unavailable"; reason: DjangoUnavailableReason };

function isTimeout(error: unknown): boolean {
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "TimeoutError"
  );
}

// A header value that cannot break the request: no control characters, bounded length.
function headerSafe(value: string | null | undefined, maxLength: number): string | null {
  if (typeof value !== "string" || value === "" || NOT_HEADER_SAFE.test(value)) {
    return null;
  }
  return value.slice(0, maxLength);
}

// A `return_path` goes out already sanitized (AC-IDA-19): Django would replace a hostile one, but
// it refuses some with 400 (DRF rejects U+0000) and the person must land on "Inicio" instead.
function outgoingBody(body: unknown): unknown {
  if (typeof body === "object" && body !== null && "return_path" in body) {
    const { return_path: returnPath } = body as { return_path: unknown };
    if (returnPath !== null && returnPath !== undefined) {
      return { ...body, return_path: sanitizeReturnPath(returnPath) };
    }
  }
  return body;
}

export async function callDjangoBff<P extends BffPath>(
  call: DjangoBffCall<P>,
): Promise<DjangoBffOutcome> {
  let target: URL;
  let credential: string;
  try {
    const base = getBackendInternalUrl();
    target = new URL(call.path, base);
    credential = getBffCredential();
  } catch {
    // Which variable is missing is in the error, never its value; it is not exposed either.
    return { kind: "unavailable", reason: "config" };
  }

  const headers = new Headers({
    accept: "application/json",
    "content-type": "application/json",
    [REQUEST_ID_HEADER]: call.requestId,
    [FORWARDED_PROTO_HEADER]: FORWARDED_PROTO,
    [BFF_CREDENTIAL_HEADER]: credential,
  });
  // Only an address client-ip.ts accepted ever gets here; still, nothing that could break a header.
  const clientIp = headerSafe(call.clientIp, 64);
  if (clientIp !== null) {
    headers.set(CLIENT_IP_HEADER, clientIp);
  }
  const userAgent = headerSafe(call.clientUserAgent, MAX_USER_AGENT_LENGTH);
  if (userAgent !== null) {
    headers.set(CLIENT_UA_HEADER, userAgent);
  }

  const timeout = AbortSignal.timeout(DJANGO_BFF_TIMEOUT_MS);
  const signal = call.signal ? AbortSignal.any([call.signal, timeout]) : timeout;
  try {
    const response = await fetch(target, {
      method: "POST",
      headers,
      body: JSON.stringify(outgoingBody(call.body)),
      redirect: "manual",
      cache: "no-store",
      signal,
    });
    return { kind: "response", response };
  } catch (error) {
    if (isTimeout(error)) {
      return { kind: "unavailable", reason: "timeout" };
    }
    return { kind: "unavailable", reason: call.signal?.aborted ? "client_abort" : "network" };
  }
}

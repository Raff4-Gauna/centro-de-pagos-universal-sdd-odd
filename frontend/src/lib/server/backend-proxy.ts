import "server-only";

import { getBackendInternalUrl } from "./env";
import { logBffRequest } from "./log";
import { REQUEST_ID_HEADER, resolveRequestId } from "./request-id";

// Pass-through from the browser to Django (RF-PLT-06, RN-PLT-16, design §3.3.3). It adds no
// business logic and does not transform bodies: it only resolves the X-Request-ID, rebuilds the
// target URL on the internal backend origin (query string preserved) and filters headers through
// allowlists in both directions. `Cookie` is never forwarded and `Set-Cookie` never returned.
// Path validation, timeout and the 400/502/504 problem responses belong to T-PLT-34.

// Request headers sent upstream besides X-Request-ID (06 adds `idempotency-key`).
const REQUEST_HEADER_ALLOWLIST = ["accept", "accept-language", "content-type"] as const;

// Response headers returned to the browser besides X-Request-ID.
const RESPONSE_HEADER_ALLOWLIST = [
  "content-type",
  "retry-after",
  "content-disposition",
  "cache-control",
] as const;

const METHODS_WITHOUT_BODY = new Set(["GET", "HEAD"]);

// `duplex` is required by Node's fetch to stream a request body but is missing from RequestInit.
type StreamingRequestInit = RequestInit & { duplex?: "half" };

function pickHeaders(source: Headers, allowlist: readonly string[], requestId: string): Headers {
  const picked = new Headers();
  for (const name of allowlist) {
    const value = source.get(name);
    if (value !== null) {
      picked.set(name, value);
    }
  }
  picked.set(REQUEST_ID_HEADER, requestId);
  return picked;
}

function backendTarget(request: Request, pathSegments: readonly string[]): URL {
  const target = new URL(`/api/${pathSegments.join("/")}`, getBackendInternalUrl());
  target.search = new URL(request.url).search;
  return target;
}

export async function proxyToBackend(
  request: Request,
  pathSegments: readonly string[],
): Promise<Response> {
  const startedAt = performance.now();
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const hasBody = !METHODS_WITHOUT_BODY.has(request.method) && request.body !== null;

  const init: StreamingRequestInit = {
    method: request.method,
    headers: pickHeaders(request.headers, REQUEST_HEADER_ALLOWLIST, requestId),
    redirect: "manual",
    cache: "no-store",
  };
  if (hasBody) {
    init.body = request.body;
    init.duplex = "half";
  }

  const upstream = await fetch(backendTarget(request, pathSegments), init);

  const response = new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: pickHeaders(upstream.headers, RESPONSE_HEADER_ALLOWLIST, requestId),
  });
  logBffRequest({
    requestId,
    method: request.method,
    status: response.status,
    durationMs: performance.now() - startedAt,
  });
  return response;
}

import "server-only";

import { getBackendInternalUrl } from "./env";
import { logBffRequest } from "./log";
import { REQUEST_ID_HEADER, resolveRequestId } from "./request-id";

// Pass-through from the browser to Django (RF-PLT-06, RN-PLT-16, design §3.3.3). It adds no
// business logic and does not transform bodies: it only resolves the X-Request-ID, rebuilds the
// target URL on the internal backend origin (query string and trailing slash preserved) and
// filters headers through allowlists in both directions. `Cookie` is never forwarded and
// `Set-Cookie` never returned. Unsafe paths and upstream failures become problem+json responses
// (design §6.2) that always carry the X-Request-ID; every request, failed or not, logs one line.

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

// Budget for the upstream exchange. The signal stays attached to the response body, so it also
// bounds how long a body may take to stream (enough for 00; long downloads will need their own).
export const UPSTREAM_TIMEOUT_MS = 30_000;

const DIGITS = /^\d+$/;
const CONTROL_CHARACTERS = /\p{Cc}/u;
const SEPARATORS = /[/\\]/;
// Percent-decoding rounds checked per segment (catches %2e, %252e, %25252e…); deeper is rejected.
const MAX_DECODE_ROUNDS = 4;

type ProblemCode = "bff.bad_path" | "bff.upstream_unavailable" | "bff.upstream_timeout";

const PROBLEMS: Record<ProblemCode, { status: number; title: string; detail?: string }> = {
  "bff.bad_path": {
    status: 400,
    title: "Ruta inválida",
    detail: "La ruta pedida no es válida.",
  },
  // No `detail` on 5xx: the cause (backend URL, network error) stays out of the response (C-06).
  "bff.upstream_unavailable": { status: 502, title: "Servicio no disponible" },
  "bff.upstream_timeout": { status: 504, title: "El servicio no respondió a tiempo" },
};

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

// A segment is safe if neither it nor any of its percent-decoded forms is empty, `.`/`..`, or
// holds a separator or control character. Malformed percent-encoding is rejected as well.
function isSafeSegment(segment: string): boolean {
  let value = segment;
  for (let round = 0; round <= MAX_DECODE_ROUNDS; round += 1) {
    if (
      value === "" ||
      value === "." ||
      value === ".." ||
      SEPARATORS.test(value) ||
      CONTROL_CHARACTERS.test(value)
    ) {
      return false;
    }
    let decoded: string;
    try {
      decoded = decodeURIComponent(value);
    } catch {
      return false;
    }
    if (decoded === value) {
      return true;
    }
    value = decoded;
  }
  return false;
}

// `/api/<segments>` with every segment percent-encoded (a decoded `#` or `?` cannot cut the path)
// and the request's trailing slash kept: DRF routes end in `/` (Q-061). Null if any is unsafe.
function backendPath(request: Request, pathSegments: readonly string[]): string | null {
  const segments = [...pathSegments];
  let trailingSlash = new URL(request.url).pathname.endsWith("/");
  if (segments.at(-1) === "") {
    segments.pop();
    trailingSlash = true;
  }
  if (!segments.every(isSafeSegment)) {
    return null;
  }
  const joined = segments.map(encodeURIComponent).join("/");
  return `/api/${joined}${joined && trailingSlash ? "/" : ""}`;
}

// Final check on the resolved URL: same origin as BACKEND_INTERNAL_URL and under `/api/`.
export function isSafeBackendTarget(target: URL, base: URL): boolean {
  return target.origin === base.origin && target.pathname.startsWith("/api/");
}

function upstreamInit(request: Request, requestId: string): StreamingRequestInit {
  const headers = pickHeaders(request.headers, REQUEST_HEADER_ALLOWLIST, requestId);
  const init: StreamingRequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
    // Aborts the upstream call when the browser disconnects or the budget runs out.
    signal: AbortSignal.any([request.signal, AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)]),
  };
  if (!METHODS_WITHOUT_BODY.has(request.method) && request.body !== null) {
    init.body = request.body;
    init.duplex = "half";
    // Without it undici streams with `Transfer-Encoding: chunked` and gunicorn/Django read an
    // empty body. Only a plain digit string is forwarded.
    const contentLength = request.headers.get("content-length");
    if (contentLength !== null && DIGITS.test(contentLength)) {
      headers.set("content-length", contentLength);
    }
  }
  return init;
}

function isTimeout(error: unknown): boolean {
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "TimeoutError"
  );
}

async function forward(
  request: Request,
  pathSegments: readonly string[],
  requestId: string,
): Promise<Response | ProblemCode> {
  const path = backendPath(request, pathSegments);
  if (path === null) {
    return "bff.bad_path";
  }
  let base: URL;
  try {
    base = getBackendInternalUrl();
  } catch {
    // Missing or invalid configuration; the message (never the value) is not exposed either.
    return "bff.upstream_unavailable";
  }
  const target = new URL(path, base);
  target.search = new URL(request.url).search;
  if (!isSafeBackendTarget(target, base)) {
    return "bff.bad_path";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, upstreamInit(request, requestId));
  } catch (error) {
    // Connection refused, DNS failure, reset, or the browser went away: all are "unavailable".
    return isTimeout(error) ? "bff.upstream_timeout" : "bff.upstream_unavailable";
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: pickHeaders(upstream.headers, RESPONSE_HEADER_ALLOWLIST, requestId),
  });
}

function problemResponse(code: ProblemCode, requestId: string): Response {
  const { status, title, detail } = PROBLEMS[code];
  const body = {
    type: `urn:hub:problem:${code}`,
    title,
    status,
    code,
    detail,
    request_id: requestId,
  };
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/problem+json",
      "cache-control": "no-store",
      [REQUEST_ID_HEADER]: requestId,
    },
  });
}

export async function proxyToBackend(
  request: Request,
  pathSegments: readonly string[],
): Promise<Response> {
  const startedAt = performance.now();
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));

  const outcome = await forward(request, pathSegments, requestId);
  const response = outcome instanceof Response ? outcome : problemResponse(outcome, requestId);

  logBffRequest({
    requestId,
    method: request.method,
    status: response.status,
    durationMs: performance.now() - startedAt,
    code: outcome instanceof Response ? undefined : outcome,
  });
  return response;
}

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
export const REQUEST_HEADER_ALLOWLIST = ["accept", "accept-language", "content-type"] as const;

// Always sent to the backend, with this constant value (Q-065, design §3.2.2): the internal hop is
// plain HTTP and `SECURE_SSL_REDIRECT` would answer every request with a 301 to
// `https://backend/...`. It stays out of the allowlist on purpose: what the browser sends is dropped.
const FORWARDED_PROTO_HEADER = "x-forwarded-proto";
const FORWARDED_PROTO = "https";

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

type ProblemCode =
  "bff.bad_path" | "bff.length_required" | "bff.upstream_unavailable" | "bff.upstream_timeout";

// Why a 502 happened. Log-only: it never reaches the response.
type UnavailableReason = "config" | "network" | "client_abort";

type Problem = { code: ProblemCode; reason?: UnavailableReason };

const PROBLEMS: Record<ProblemCode, { status: number; title: string; detail?: string }> = {
  "bff.bad_path": {
    status: 400,
    title: "Ruta inválida",
    detail: "La ruta pedida no es válida.",
  },
  "bff.length_required": {
    status: 411,
    title: "Falta la longitud del cuerpo",
    detail: "La petición tiene cuerpo pero no un Content-Length válido.",
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
// holds a separator or control character. Segments arrive already decoded once by Next, so a
// round that fails to decode here means a literal `%` (`a%25b` → `a%b`): decoding stops and the
// segment is accepted, since it is re-encoded on the way out and cannot turn into `.`, `..` or a
// separator. Malformed encoding in the raw path itself is rejected in `backendPath`.
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
      return true;
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
  const rawPath = new URL(request.url).pathname;
  let trailingSlash = rawPath.endsWith("/");
  if (segments.at(-1) === "") {
    segments.pop();
    trailingSlash = true;
  }
  try {
    // First decoding round: the path exactly as the browser sent it must be well formed.
    decodeURIComponent(rawPath);
    if (!segments.every(isSafeSegment)) {
      return null;
    }
    // Throws on a lone surrogate, which is a bad path too (not a 500 without a log line).
    const joined = segments.map(encodeURIComponent).join("/");
    return `/api/${joined}${joined && trailingSlash ? "/" : ""}`;
  } catch {
    return null;
  }
}

// Final check on the resolved URL: same origin as BACKEND_INTERNAL_URL and under `/api/`.
export function isSafeBackendTarget(target: URL, base: URL): boolean {
  return target.origin === base.origin && target.pathname.startsWith("/api/");
}

// How the incoming body is framed (RFC 9112 §6.3). Next hands every non-GET/HEAD request over
// with a `body` stream, even a DELETE without one, so the stream alone does not tell: no
// `content-length` and no `transfer-encoding` means there is no body.
// - `sized`: plain-digit `content-length` → the body is forwarded with it.
// - `unsized`: chunked, or a `content-length` that is not plain digits → 411 before the backend:
//   undici would stream it with `Transfer-Encoding: chunked` and gunicorn/Django read it empty.
type BodyFraming = { kind: "none" } | { kind: "sized"; length: string } | { kind: "unsized" };

function bodyFraming(request: Request): BodyFraming {
  if (METHODS_WITHOUT_BODY.has(request.method) || request.body === null) {
    return { kind: "none" };
  }
  if (request.headers.has("transfer-encoding")) {
    return { kind: "unsized" };
  }
  const contentLength = request.headers.get("content-length");
  if (contentLength === null) {
    return { kind: "none" };
  }
  return DIGITS.test(contentLength)
    ? { kind: "sized", length: contentLength }
    : { kind: "unsized" };
}

function upstreamInit(request: Request, requestId: string): StreamingRequestInit {
  const headers = pickHeaders(request.headers, REQUEST_HEADER_ALLOWLIST, requestId);
  headers.set(FORWARDED_PROTO_HEADER, FORWARDED_PROTO);
  const init: StreamingRequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
    // Aborts the upstream call when the browser disconnects or the budget runs out.
    signal: AbortSignal.any([request.signal, AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)]),
  };
  const framing = bodyFraming(request);
  if (framing.kind === "sized") {
    init.body = request.body;
    init.duplex = "half";
    headers.set("content-length", framing.length);
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
): Promise<Response | Problem> {
  const path = backendPath(request, pathSegments);
  if (path === null) {
    return { code: "bff.bad_path" };
  }
  if (bodyFraming(request).kind === "unsized") {
    return { code: "bff.length_required" };
  }
  let base: URL;
  try {
    base = getBackendInternalUrl();
  } catch {
    // Missing or invalid configuration; the message (never the value) is not exposed either.
    return { code: "bff.upstream_unavailable", reason: "config" };
  }
  const target = new URL(path, base);
  target.search = new URL(request.url).search;
  if (!isSafeBackendTarget(target, base)) {
    return { code: "bff.bad_path" };
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, upstreamInit(request, requestId));
  } catch (error) {
    if (isTimeout(error)) {
      return { code: "bff.upstream_timeout" };
    }
    // Connection refused, DNS failure, reset… or the browser went away (nobody gets the answer).
    const reason = request.signal.aborted ? "client_abort" : "network";
    return { code: "bff.upstream_unavailable", reason };
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
  const problem = outcome instanceof Response ? undefined : outcome;
  const response = outcome instanceof Response ? outcome : problemResponse(outcome.code, requestId);

  logBffRequest({
    requestId,
    method: request.method,
    status: response.status,
    durationMs: performance.now() - startedAt,
    code: problem?.code,
    reason: problem?.reason,
    // A browser that hung up is not an upstream failure.
    level: problem?.reason === "client_abort" ? "info" : undefined,
  });
  return response;
}

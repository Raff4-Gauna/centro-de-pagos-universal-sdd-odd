import "server-only";

import { type StreamingRequestInit, type UpstreamSend, proxyToBackend } from "./backend-proxy";
import { clientIpOf } from "./client-ip";
import { COOKIE_NAMES, type BffCookie, serializeCookie } from "./cookies";
import { checkCsrf, requestCookieValues } from "./csrf";
import { logBffRequest } from "./log";
import { type BffProblemCode, bffProblem } from "./problem";
import { cookiesAfterRefresh, cookiesAfterRejectedRefresh, refreshSession } from "./refresh";
import { REQUEST_ID_HEADER, resolveRequestId } from "./request-id";

// The session side of the catch-all proxy (RN-IDA-12, RN-IDA-20, AC-IDA-18/26/28, design.md §4.4,
// §6.3, ADR-0004). backend-proxy.ts stays a plain pass-through; this module adds, in order:
// 1. a denylist: `auth/bff/**` and `auth/google/**` are `404 not_found`, Django never hears of them;
// 2. the CSRF check of every unsafe method (`403 bff.csrf_failed`);
// 3. the Bearer: `__Host-cpu_at` becomes `Authorization`. Without it and with `__Host-cpu_rt`, the
//    session is refreshed first (coalesced per instance, refresh.ts);
// 4. one refresh and one retry when Django answers `401 token_expired | token_invalid` (the 401 of
//    authentication happens before the view, so a retried mutation is not duplicated);
// 5. the end of the session: `session_revoked`, or a refresh Django rejects, clears the session
//    cookies and answers `401 session_revoked`; the api-client then goes to "Ingresar".
// The browser's `cookie`, `authorization` and `x-hub-*` never travel (backend-proxy's allowlist).
// No token reaches a log line, an error or a body: they only travel to Django in `Authorization`
// or the refresh body, and back in HttpOnly cookies.

const DENIED_PREFIXES: readonly (readonly [string, string])[] = [
  ["auth", "bff"],
  ["auth", "google"],
];
const MAX_DECODE_ROUNDS = 4;
// Django's codes for a Bearer it does not take (design.md §6.2). The first two are worth one
// refresh; `session_revoked` is final.
const RETRYABLE = new Set(["token_expired", "token_invalid"]);
const SESSION_ENDED = new Set(["token_expired", "token_invalid", "session_revoked"]);
// A JWT in base64url with dots; anything else is not written into a header.
const ACCESS_TOKEN_SHAPE = /^[A-Za-z0-9._~+/=-]{1,4096}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ORGANIZATION_HEADER = "x-organization-id";

// Lower case and percent-decoded until stable, so `Auth/%62ff` is denied like `auth/bff`.
function normalized(segment: string): string {
  let value = segment;
  for (let round = 0; round < MAX_DECODE_ROUNDS; round += 1) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(value);
    } catch {
      break;
    }
    if (decoded === value) {
      break;
    }
    value = decoded;
  }
  return value.toLowerCase();
}

export function isDeniedPath(pathSegments: readonly string[]): boolean {
  const [first, second] = pathSegments.map(normalized);
  return DENIED_PREFIXES.some(([a, b]) => first === a && second === b);
}

// The one value of a session cookie; absent, empty or repeated (ambiguous) is `null`.
function sessionCookie(headers: Headers, name: string): string | null {
  const values = requestCookieValues(headers, name);
  return values.length === 1 && values[0] !== "" ? values[0]! : null;
}

async function problemCode(response: Response): Promise<{ code: unknown; text: string }> {
  const text = await response.text();
  try {
    const body: unknown = JSON.parse(text);
    return {
      code:
        typeof body === "object" && body !== null ? (body as { code?: unknown }).code : undefined,
      text,
    };
  } catch {
    return { code: undefined, text };
  }
}

// A 401 read to learn its code, given back with the same status and headers.
function rebuilt(text: string, response: Response): Response {
  return new Response(text, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

class SessionExchange {
  private access: string | null;
  private readonly refreshToken: string | null;
  private readonly csrf: string | null;
  private refreshed = false;
  // A second copy of the body, for the retry; only kept while a retry is possible.
  private readonly spare: Request | null;
  cookies: BffCookie[] = [];

  constructor(private readonly request: Request) {
    const access = sessionCookie(request.headers, COOKIE_NAMES.access);
    this.access = access !== null && ACCESS_TOKEN_SHAPE.test(access) ? access : null;
    this.refreshToken = sessionCookie(request.headers, COOKIE_NAMES.refresh);
    this.csrf = sessionCookie(request.headers, COOKIE_NAMES.csrf);
    this.spare = this.refreshToken !== null && request.body !== null ? request.clone() : null;
  }

  readonly send: UpstreamSend = async (target, init) => {
    const organization = init.headers.get(ORGANIZATION_HEADER);
    if (organization !== null && !UUID.test(organization)) {
      init.headers.delete(ORGANIZATION_HEADER);
    }
    const requestId = init.headers.get(REQUEST_ID_HEADER) ?? resolveRequestId(null);
    if (this.access === null && this.refreshToken !== null) {
      const failure = await this.refresh(requestId);
      if (failure !== null) {
        return failure;
      }
    }
    const first = await this.fetchWithBearer(target, init);
    if (first.status !== 401) {
      return first;
    }
    const { code, text } = await problemCode(first);
    const firstResponse = rebuilt(text, first);
    if (!RETRYABLE.has(code as string) || this.refreshed || this.refreshToken === null) {
      return this.final(firstResponse, code);
    }
    const failure = await this.refresh(requestId);
    if (failure !== null) {
      return failure;
    }
    const retryInit: StreamingRequestInit = { ...init, headers: new Headers(init.headers) };
    if (init.body !== undefined && init.body !== null) {
      retryInit.body = this.spare?.body ?? null;
    }
    const retried = await this.fetchWithBearer(target, retryInit);
    if (retried.status !== 401) {
      return retried;
    }
    const last = await problemCode(retried);
    return this.final(rebuilt(last.text, retried), last.code);
  };

  // Frees the spare copy of the body when no retry used it.
  async release(): Promise<void> {
    try {
      await this.spare?.body?.cancel();
    } catch {
      // Already used by the retry.
    }
  }

  private fetchWithBearer(target: URL, init: StreamingRequestInit): Promise<Response> {
    if (this.access === null) {
      init.headers.delete("authorization");
    } else {
      init.headers.set("authorization", `Bearer ${this.access}`);
    }
    return fetch(target, init);
  }

  // A 401 that ends the session clears its cookies; any other answer goes back as is.
  private final(response: Response, code: unknown): Response {
    if (SESSION_ENDED.has(code as string)) {
      this.cookies = cookiesAfterRejectedRefresh();
    }
    return response;
  }

  // `null` when the session goes on with a new access token, otherwise the answer to give.
  private async refresh(requestId: string): Promise<Response | null> {
    this.refreshed = true;
    let clientIp: string | null;
    try {
      clientIp = clientIpOf(this.request);
    } catch {
      return bffProblem("bff.upstream_unavailable", requestId);
    }
    const outcome = await refreshSession({
      refreshToken: this.refreshToken!,
      requestId,
      clientIp,
      clientUserAgent: this.request.headers.get("user-agent"),
    });
    switch (outcome.kind) {
      case "refreshed":
        this.access = outcome.session.accessToken;
        this.cookies = cookiesAfterRefresh(outcome.session, this.csrf);
        return null;
      case "rejected":
        this.cookies = cookiesAfterRejectedRefresh();
        return bffProblem("session_revoked", requestId);
      case "rate_limited": {
        const response = bffProblem("rate_limited", requestId);
        if (outcome.retryAfter !== null) {
          response.headers.set("retry-after", outcome.retryAfter);
        }
        return response;
      }
      default:
        return bffProblem(
          outcome.reason === "timeout" ? "bff.upstream_timeout" : "bff.upstream_unavailable",
          requestId,
        );
    }
  }
}

// An answer given without calling Django, with its one log line (`reason` names the failed check).
function refusal(
  request: Request,
  code: BffProblemCode,
  startedAt: number,
  reason?: string,
): Response {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const response = bffProblem(code, requestId);
  logBffRequest({
    requestId,
    method: request.method,
    status: response.status,
    durationMs: performance.now() - startedAt,
    code,
    reason,
  });
  return response;
}

// The catch-all `/api/[...path]` with the session (route.ts).
export async function proxyWithSession(
  request: Request,
  pathSegments: readonly string[],
): Promise<Response> {
  const startedAt = performance.now();
  if (isDeniedPath(pathSegments)) {
    return refusal(request, "not_found", startedAt);
  }
  const csrf = checkCsrf(request);
  if (!csrf.ok) {
    return refusal(request, "bff.csrf_failed", startedAt, csrf.reason);
  }
  const exchange = new SessionExchange(request);
  const response = await proxyToBackend(request, pathSegments, exchange.send);
  await exchange.release();
  if (exchange.cookies.length > 0) {
    for (const cookie of exchange.cookies) {
      response.headers.append("set-cookie", serializeCookie(cookie));
    }
    // A response that writes the session is never stored by a cache.
    response.headers.set("cache-control", "no-store");
  }
  return response;
}

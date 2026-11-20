import createClient, { type Client, type ClientOptions, type Middleware } from "openapi-fetch";

import type { paths } from "@/types/api";

import { apiErrorFromResponse, isProblemResponse, networkApiError, parseProblem } from "./problem";

// The single HTTP client of the frontend (RF-PLT-15, ADR-0005, 07 §3.1), typed with the `paths`
// generated from specs/_contracts/openapi.yaml (`pnpm openapi:types`). It only talks to the BFF on
// the same origin (Q-050, RN-PLT-16): the base URL is empty, so every path (`/api/...`) resolves
// against the page's own origin and the browser never learns the backend's address. It runs in
// the browser; server code reaches Django through lib/server, not through this client.
// Every non-2xx response is thrown as an `ApiError` (lib/problem.ts), so TanStack Query sees a
// failed query or mutation, never `{ error }` data to forget to check.
//
// The session (SPEC-01, design.md §4.4, §7.2): the BFF holds the tokens in HttpOnly cookies the
// client never sees. The client only echoes the readable `__Host-cpu_csrf` cookie in X-CSRF-Token
// on every unsafe method (double submit, RN-IDA-13), and on a `401` (the BFF could not refresh the
// session) it sends the browser to "Ingresar", keeping only the internal path to come back to.
//
// The active organization (SPEC-02 design.md §3.9, Q-119 b, ADR-0004 §7): a tenant-scoped request
// names its company in `X-Organization-Id`, taken from the `['org', orgId, …]` key of its own query
// (`orgHeaderFromKey`) or, for a mutation, from the company the screen shows. There is no shared
// "current company" the client fills in: a request without the header fails closed (`400
// organization_required`), it never goes out with the company of another render.

export const API_BASE_URL = "";

const API_PATH_PREFIX = "/api/";

export const CSRF_COOKIE = "__Host-cpu_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const LOGIN_PATH = "/login";

// The one value of cookie `name` in a `document.cookie` string; absent, empty or repeated → null.
export function cookieValue(cookieString: string, name: string): string | null {
  const values: string[] = [];
  for (const pair of cookieString.split(";")) {
    const separator = pair.indexOf("=");
    if (separator !== -1 && pair.slice(0, separator).trim() === name) {
      values.push(pair.slice(separator + 1).trim());
    }
  }
  return values.length === 1 && values[0] !== "" ? values[0]! : null;
}

function readCsrfCookie(): string | null {
  return typeof document === "undefined" ? null : cookieValue(document.cookie, CSRF_COOKIE);
}

// Where a `401` sends the browser: "Ingresar" with `session_expired` and the current path and
// query (never the origin or the fragment; the BFF sanitizes it again). `null` on "Ingresar".
export function sessionExpiredUrl(location: Pick<Location, "pathname" | "search">): string | null {
  if (location.pathname === LOGIN_PATH || location.pathname.startsWith(`${LOGIN_PATH}/`)) {
    return null;
  }
  const query = new URLSearchParams({
    error: "session_expired",
    return_to: `${location.pathname}${location.search}`,
  });
  return `${LOGIN_PATH}?${query.toString()}`;
}

function goToLogin(url: string): void {
  window.location.assign(url);
}

// A per-request `baseUrl` (or an absolute path) could point the client somewhere else: anything
// that does not resolve to `/api/...` on the page's origin is refused before it is sent.
function assertSameOriginApi(request: Request): void {
  const target = new URL(request.url);
  if (target.origin !== window.location.origin || !target.pathname.startsWith(API_PATH_PREFIX)) {
    throw new Error("api-client: only same-origin /api/ requests are allowed");
  }
}

// A DOMException is not always an `Error` instance (jsdom, other realms): match on the name.
function isAbort(error: unknown): boolean {
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "AbortError"
  );
}

export const problemMiddleware: Middleware = {
  onRequest({ request }) {
    assertSameOriginApi(request);
  },
  async onResponse({ response }) {
    if (!response.ok) {
      throw await apiErrorFromResponse(response);
    }
  },
  onError({ error }) {
    // A cancelled query keeps its AbortError as is (rethrown: openapi-fetch only passes on
    // `Error` instances), so TanStack Query treats it as a cancellation, not a failure.
    if (isAbort(error)) {
      throw error;
    }
    return networkApiError();
  },
};

// Registered after `problemMiddleware`: openapi-fetch runs `onResponse` in reverse order, so this
// one sees the `401` before it is thrown as an `ApiError`.
export function sessionMiddleware(
  readCsrfToken: () => string | null,
  onSessionExpired: (url: string) => void,
): Middleware {
  return {
    onRequest({ request }) {
      if (!SAFE_METHODS.has(request.method.toUpperCase())) {
        const token = readCsrfToken();
        if (token !== null) {
          request.headers.set(CSRF_HEADER, token);
        }
      }
    },
    onResponse({ response }) {
      if (response.status === 401) {
        const url = sessionExpiredUrl(window.location);
        if (url !== null) {
          onSessionExpired(url);
        }
      }
    },
  };
}

export const ORGANIZATION_HEADER = "X-Organization-Id";

// Root of every query key of tenant-scoped data: `['org', orgId, …]`. Changing company removes the
// whole root, so no screen ever shows data of the company the tab left (design.md §3.9).
export const ORG_QUERY_SCOPE = "org";

export function orgQueryKey<const Parts extends readonly unknown[]>(
  organizationId: string,
  ...parts: Parts
) {
  return [ORG_QUERY_SCOPE, organizationId, ...parts] as const;
}

export type OrganizationHeader = { [ORGANIZATION_HEADER]: string };

// The header of a request about `organizationId` (`params.header` of a typed call). It is not an
// authorization: Django revalidates the membership on every request (RN-TEN-03).
export function organizationHeader(organizationId: string): OrganizationHeader {
  return { [ORGANIZATION_HEADER]: organizationId };
}

// The header of a query, read from its own key: the company the request names is, by
// construction, the one its data is cached under. A key outside `['org', orgId, …]` is a bug.
export function orgHeaderFromKey(queryKey: readonly unknown[]): OrganizationHeader {
  const [scope, organizationId] = queryKey;
  if (scope !== ORG_QUERY_SCOPE || typeof organizationId !== "string" || organizationId === "") {
    throw new Error("api-client: a tenant-scoped query needs an ['org', orgId, …] key");
  }
  return organizationHeader(organizationId);
}

// The two answers about the organization itself that the whole shell reacts to (design.md §3.9).
export const ORGANIZATION_ERROR_CODES = [
  "organization_not_found",
  "organization_suspended",
] as const;
export type OrganizationErrorCode = (typeof ORGANIZATION_ERROR_CODES)[number];
export type OrganizationErrorEvent = Readonly<{
  code: OrganizationErrorCode;
  // The organization the request was sent for: a late answer about a company the tab already left
  // is told apart from one about the company it shows.
  organizationId: string | null;
}>;
type OrganizationErrorListener = (event: OrganizationErrorEvent) => void;

const organizationErrorListeners = new Set<OrganizationErrorListener>();

export function subscribeOrganizationErrors(listener: OrganizationErrorListener): () => void {
  organizationErrorListeners.add(listener);
  return () => {
    organizationErrorListeners.delete(listener);
  };
}

function notifyOrganizationError(event: OrganizationErrorEvent): void {
  for (const listener of organizationErrorListeners) {
    listener(event);
  }
}

function isOrganizationErrorCode(code: string): code is OrganizationErrorCode {
  return (ORGANIZATION_ERROR_CODES as readonly string[]).includes(code);
}

// Registered after `problemMiddleware`, like `sessionMiddleware`, so it reads a copy of the body
// before the response is thrown as an `ApiError`. It never adds nor changes the header.
export function organizationMiddleware(onOrganizationError: OrganizationErrorListener): Middleware {
  return {
    async onResponse({ request, response }) {
      if ((response.status !== 404 && response.status !== 409) || !isProblemResponse(response)) {
        return;
      }
      let problem: ReturnType<typeof parseProblem> = null;
      try {
        problem = parseProblem(await response.clone().json());
      } catch {
        return;
      }
      if (problem !== null && isOrganizationErrorCode(problem.code)) {
        const organizationId = request.headers.get(ORGANIZATION_HEADER);
        onOrganizationError({ code: problem.code, organizationId });
      }
    },
  };
}

export type ApiClient = Client<paths>;

export type ApiClientOptions = Pick<ClientOptions, "fetch" | "Request"> & {
  readCsrfToken?: () => string | null;
  onSessionExpired?: (url: string) => void;
  onOrganizationError?: OrganizationErrorListener;
};

// Everything is injectable for tests only; production uses the browser's.
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const {
    readCsrfToken = readCsrfCookie,
    onSessionExpired = goToLogin,
    onOrganizationError = notifyOrganizationError,
    ...fetchOptions
  } = options;
  const client = createClient<paths>({ ...fetchOptions, baseUrl: API_BASE_URL });
  client.use(
    problemMiddleware,
    sessionMiddleware(readCsrfToken, onSessionExpired),
    organizationMiddleware(onOrganizationError),
  );
  return client;
}

export const apiClient: ApiClient = createApiClient();

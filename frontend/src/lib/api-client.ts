import createClient, { type Client, type ClientOptions, type Middleware } from "openapi-fetch";

import type { paths } from "@/types/api";

import { apiErrorFromResponse, networkApiError } from "./problem";

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

export type ApiClient = Client<paths>;

export type ApiClientOptions = Pick<ClientOptions, "fetch" | "Request"> & {
  readCsrfToken?: () => string | null;
  onSessionExpired?: (url: string) => void;
};

// Everything is injectable for tests only; production uses the browser's.
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const { readCsrfToken = readCsrfCookie, onSessionExpired = goToLogin, ...fetchOptions } = options;
  const client = createClient<paths>({ ...fetchOptions, baseUrl: API_BASE_URL });
  client.use(problemMiddleware, sessionMiddleware(readCsrfToken, onSessionExpired));
  return client;
}

export const apiClient: ApiClient = createApiClient();

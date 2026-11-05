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

export const API_BASE_URL = "";

const API_PATH_PREFIX = "/api/";

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

export type ApiClient = Client<paths>;

// `fetch`/`Request` are injectable for tests only; production uses the browser's.
export function createApiClient(options: Pick<ClientOptions, "fetch" | "Request"> = {}): ApiClient {
  const client = createClient<paths>({ ...options, baseUrl: API_BASE_URL });
  client.use(problemMiddleware);
  return client;
}

export const apiClient: ApiClient = createApiClient();

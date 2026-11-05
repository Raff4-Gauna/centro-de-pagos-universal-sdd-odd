import { isServer, QueryClient } from "@tanstack/react-query";

// TanStack Query defaults (design.md §3.3.3, 07 §3.1). Mutations never retry: a repeated action
// (a charge, a refund) must be an explicit user decision, not a side effect of the client.
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
      mutations: { retry: 0 },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

// Server: a new client per request, so no cache is shared between users. Browser: one client for the
// whole session, so a re-render (or React suspending during the first render) keeps the cache.
export function getQueryClient(): QueryClient {
  if (isServer) {
    return makeQueryClient();
  }
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

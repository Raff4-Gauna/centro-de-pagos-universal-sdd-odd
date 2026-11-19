"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient, type ApiClient } from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";
import type { components } from "@/types/api";

// The person's own active sessions (RF-IDA-07, AC-IDA-33, design.md §6.2): browser and OS
// summarized, start and last use, the current one marked; never an IP (Q-113). The list has no
// limit and is paginated (SPEC-00), so every page is read: the screen shows one table, with no
// pagination to word, and the current session is never left on a page not shown.
export type Session = components["schemas"]["Session"];

export const SESSIONS_QUERY_KEY = ["identity", "sessions"] as const;

// The page number of a `next` link (a relative path with `?page=N`), or null without one.
function pageOf(next: string): number | null {
  const value = new URL(next, "http://next.invalid").searchParams.get("page");
  const page = value === null ? Number.NaN : Number(value);
  return Number.isInteger(page) ? page : null;
}

export async function fetchAllSessions(
  client: ApiClient = apiClient,
  signal?: AbortSignal,
): Promise<Session[]> {
  const sessions: Session[] = [];
  let page: number | undefined;
  for (;;) {
    const { data, response } = await client.GET("/api/auth/sessions/", {
      params: { query: page === undefined ? {} : { page } },
      signal,
    });
    if (data === undefined) {
      throw await apiErrorFromResponse(response);
    }
    sessions.push(...data.results);
    if (!data.next) {
      return sessions;
    }
    // A `next` that does not move forward would loop forever: an unexpected response.
    const nextPage = pageOf(data.next);
    if (nextPage === null || nextPage <= (page ?? 1)) {
      throw await apiErrorFromResponse(response);
    }
    page = nextPage;
  }
}

export function useSessions() {
  return useQuery<Session[], ApiError>({
    queryKey: SESSIONS_QUERY_KEY,
    queryFn: ({ signal }) => fetchAllSessions(apiClient, signal),
  });
}

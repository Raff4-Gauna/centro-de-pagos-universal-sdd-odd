"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient, type ApiClient } from "@/lib/api-client";
import { ApiError } from "@/lib/problem";

import { SESSIONS_QUERY_KEY } from "./useSessions";

// "Cerrar sesión" on another session of the person (RF-IDA-07, design.md §6.2): its id travels
// only in the request path of the typed client, never in the page URL nor in a log. The current
// session is never closed here: it goes through the BFF logout (`useLogout`), which also clears
// the cookies.
//
// A `404 not_found` means the session had already ended, or is not the person's (Q-129 a): the
// person wanted it closed and it is, so it counts as done, never as an error to fix. Either way
// the list is read again, so the row disappears without a success message.
export type RevokeOutcome = "revoked" | "already_ended";

export async function revokeSession(client: ApiClient, sessionId: string): Promise<RevokeOutcome> {
  try {
    await client.POST("/api/auth/sessions/{session_id}/revoke/", {
      params: { path: { session_id: sessionId } },
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return "already_ended";
    }
    throw error;
  }
  return "revoked";
}

export function useRevokeSession(client: ApiClient = apiClient) {
  const queryClient = useQueryClient();
  return useMutation<RevokeOutcome, ApiError, string>({
    mutationFn: (sessionId) => revokeSession(client, sessionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY }),
  });
}

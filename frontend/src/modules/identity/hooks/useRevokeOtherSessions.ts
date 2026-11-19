"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient, type ApiClient } from "@/lib/api-client";
import type { ApiError } from "@/lib/problem";

import { SESSIONS_QUERY_KEY } from "./useSessions";

// "Cerrar las demás" (RF-IDA-07, AC-IDA-33, design.md §6.2): the server revokes every active
// session of the person but the one making the request, so only the current one stays. On the
// `204` the list is read again; there is no success message (Q-129 a).
export async function revokeOtherSessions(client: ApiClient): Promise<void> {
  await client.POST("/api/auth/sessions/revoke-others/");
}

export function useRevokeOtherSessions(client: ApiClient = apiClient) {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () => revokeOtherSessions(client),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY }),
  });
}

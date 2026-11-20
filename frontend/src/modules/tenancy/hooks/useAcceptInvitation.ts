"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient, type ApiClient } from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";

import { clearStoredToken } from "../lib/invitation-token";
import { MY_INVITATIONS_QUERY_KEY, type AcceptedInvitation } from "./useMyInvitations";
import { ORGANIZATIONS_QUERY_KEY } from "./useOrganizations";

// Accepting an invitation with the token of its link (RN-TEN-12, AC-TEN-17, design.md §3.9, §6):
// `POST /api/invitations/accept/` with `{token}`. The route is exempt from the active
// organization, so it never sends `X-Organization-Id`; the api-client adds the CSRF header of
// every unsafe request. Only a `200` counts as accepted: the screen never shows a membership the
// server did not confirm. A `401` is the api-client's: it sends the browser to "Ingresar".
export async function acceptInvitation(
  client: ApiClient,
  token: string,
): Promise<AcceptedInvitation> {
  const { data, response } = await client.POST("/api/invitations/accept/", { body: { token } });
  if (data === undefined) {
    throw await apiErrorFromResponse(response);
  }
  return data;
}

// The stored token (lib/invitation-token.ts) goes with the backend's answer, here and not in the
// screen, so it goes even if the person already left the page. A `401` keeps it: the session died
// and "Ingresar" brings the person back to `/invitacion` to try again.
// After any answer the person's companies and invitations are dropped from the cache, not just
// marked stale: the shell that "Ir a la empresa" opens reads them again before it resolves the
// tab's company, so it never falls back to another one from an old list.
export function useAcceptInvitation(client: ApiClient = apiClient) {
  const queryClient = useQueryClient();
  return useMutation<AcceptedInvitation, ApiError, string>({
    mutationFn: (token) => acceptInvitation(client, token),
    onSettled: (_data, error) => {
      if (error?.status !== 401) {
        clearStoredToken();
      }
      queryClient.removeQueries({ queryKey: ORGANIZATIONS_QUERY_KEY });
      queryClient.removeQueries({ queryKey: MY_INVITATIONS_QUERY_KEY });
    },
  });
}

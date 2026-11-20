"use client";

import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, type ApiClient } from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";
import type { components } from "@/types/api";

import { ORGANIZATIONS_PAGE_SIZE, ORGANIZATIONS_QUERY_KEY } from "./useOrganizations";

// The person's own pending invitations, and accepting one from the session (RN-TEN-11, RF-TEN-05,
// AC-TEN-39, Q-121, Q-124, design.md §3.9). Both routes are exempt from the active organization:
// they never send `X-Organization-Id`, and the key is not under `['org', …]`, so changing company
// keeps it. The list carries company, role and expiry, never a token. Accepting has no body; the
// api-client adds the CSRF header of every unsafe request. Only a `200` from the backend counts as
// accepted: the screen never shows a membership the server did not confirm.
export type MyInvitation = components["schemas"]["MyInvitation"];
export type AcceptedInvitation = components["schemas"]["AcceptedInvitation"];

export const MY_INVITATIONS_QUERY_KEY = ["invitations", "mine"] as const;

// The largest page the backend allows (`max_page_size`, the same pagination as the companies).
export const MY_INVITATIONS_PAGE_SIZE = ORGANIZATIONS_PAGE_SIZE;

export async function fetchMyInvitations(
  client: ApiClient = apiClient,
  signal?: AbortSignal,
): Promise<MyInvitation[]> {
  const invitations: MyInvitation[] = [];
  for (let page = 1; ; page += 1) {
    const { data, response } = await client.GET("/api/invitations/mine/", {
      params: { query: { page, page_size: MY_INVITATIONS_PAGE_SIZE } },
      signal,
    });
    if (data === undefined) {
      // A 2xx without the body of the contract: an unexpected response, never an empty list.
      throw await apiErrorFromResponse(response);
    }
    invitations.push(...data.results);
    // `count` bounds the loop too: a `next` that never ends cannot keep the tab reading.
    if (!data.next || data.results.length === 0 || invitations.length >= data.count) {
      return invitations;
    }
  }
}

export function myInvitationsQueryOptions(client: ApiClient = apiClient) {
  return queryOptions<MyInvitation[], ApiError>({
    queryKey: MY_INVITATIONS_QUERY_KEY,
    queryFn: ({ signal }) => fetchMyInvitations(client, signal),
  });
}

export function useMyInvitations() {
  return useQuery(myInvitationsQueryOptions());
}

export async function acceptMyInvitation(
  client: ApiClient,
  invitationId: string,
): Promise<AcceptedInvitation> {
  const { data, response } = await client.POST("/api/invitations/{invitation_id}/accept/", {
    params: { path: { invitation_id: invitationId } },
  });
  if (data === undefined) {
    throw await apiErrorFromResponse(response);
  }
  return data;
}

// After any answer both lists are read again: on success the new company joins the selector (and
// the shell leaves "sin organización"); on an error (`invitation_invalid`, `already_member`,
// `organization_suspended`) the invitation list was stale.
export function useAcceptMyInvitation(client: ApiClient = apiClient) {
  const queryClient = useQueryClient();
  return useMutation<AcceptedInvitation, ApiError, string>({
    mutationFn: (invitationId) => acceptMyInvitation(client, invitationId),
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ORGANIZATIONS_QUERY_KEY }),
        queryClient.invalidateQueries({ queryKey: MY_INVITATIONS_QUERY_KEY }),
      ]);
    },
  });
}

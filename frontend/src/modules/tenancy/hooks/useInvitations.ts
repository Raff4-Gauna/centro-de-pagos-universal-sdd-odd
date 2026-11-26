"use client";

import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  apiClient,
  type ApiClient,
  organizationHeader,
  orgHeaderFromKey,
  orgQueryKey,
} from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";
import type { components } from "@/types/api";

import type { InviteRequest } from "../lib/invite-form";
import { currentOrganizationQueryKey } from "./useCurrentOrganizationDetails";
import { ORGANIZATIONS_PAGE_SIZE } from "./useOrganizations";

// The pending invitations of the active company (RF-TEN-05, spec §14, design.md §3.9, §4.3, §6):
// list, invite, resend and revoke. Each row brings the `allowed_actions` the backend lets through
// now; the UI offers only those and the backend decides again under its lock. The list query names
// its company from its own `['org', orgId, 'invitations']` key (`orgHeaderFromKey`); a mutation
// names the company the dialog was opened for.
//
// The link (AC-TEN-24, RNF-TEN-03, Q-207, C-06): the `201` of inviting and of resending is the only
// answer that carries the token, inside `accept_url`. It never enters TanStack Query: the mutation
// takes it out of the answer before returning, so neither the mutation cache nor any query keeps
// it, and hands it to the `onLink` of the dialog that asked, which keeps it in its own state only
// (InvitationLinkDialog). If that dialog is gone by then (closed, company switched) the link is
// dropped: resending issues a new one. It is never written to the URL, storage or a log.
export type Invitation = components["schemas"]["OrganizationInvitation"];
type CreatedInvitation = components["schemas"]["CreatedInvitation"];

// What the link dialog shows, once.
export type InvitationLink = Readonly<{ email: string; expiresAt: string; url: string }>;
export type OnInvitationLink = (link: InvitationLink) => void;

export const INVITATIONS_PAGE_SIZE = ORGANIZATIONS_PAGE_SIZE;

export function invitationsQueryKey(organizationId: string) {
  return orgQueryKey(organizationId, "invitations");
}

type InvitationsQueryKey = ReturnType<typeof invitationsQueryKey>;

export async function fetchInvitations(
  client: ApiClient,
  queryKey: InvitationsQueryKey,
  signal?: AbortSignal,
): Promise<Invitation[]> {
  const invitations: Invitation[] = [];
  for (let page = 1; ; page += 1) {
    const { data, response } = await client.GET("/api/invitations/", {
      params: {
        header: orgHeaderFromKey(queryKey),
        query: { page, page_size: INVITATIONS_PAGE_SIZE },
      },
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

export function invitationsQueryOptions(organizationId: string, client: ApiClient = apiClient) {
  return queryOptions<Invitation[], ApiError, Invitation[], InvitationsQueryKey>({
    queryKey: invitationsQueryKey(organizationId),
    queryFn: ({ queryKey, signal }) => fetchInvitations(client, queryKey, signal),
  });
}

// Disabled while the tab has no company yet: a request without the header is never sent.
export function useInvitations(organizationId: string | null) {
  return useQuery({
    ...invitationsQueryOptions(organizationId ?? ""),
    enabled: organizationId !== null,
  });
}

// The `201` with its link: a 2xx without one is a failure the client did not throw (an answer
// that is not problem+json becomes the generic client error, without its content).
async function unwrapCreated(result: {
  data?: CreatedInvitation;
  response: Response;
}): Promise<CreatedInvitation> {
  const { data, response } = result;
  if (data === undefined || typeof data.accept_url !== "string" || data.accept_url === "") {
    throw await apiErrorFromResponse(response);
  }
  return data;
}

// The link leaves the answer here: what is returned (and kept by the mutation) has no token.
function handOver(created: CreatedInvitation, onLink: OnInvitationLink): Invitation {
  const { accept_url: url, ...invitation } = created;
  onLink({ email: invitation.email, expiresAt: invitation.expires_at, url });
  return invitation;
}

export async function createInvitation(
  client: ApiClient,
  organizationId: string,
  body: InviteRequest,
): Promise<CreatedInvitation> {
  return unwrapCreated(
    await client.POST("/api/invitations/", {
      params: { header: organizationHeader(organizationId) },
      body,
    }),
  );
}

export async function resendInvitation(
  client: ApiClient,
  organizationId: string,
  invitationId: string,
): Promise<CreatedInvitation> {
  return unwrapCreated(
    await client.POST("/api/invitations/{id}/resend/", {
      params: { header: organizationHeader(organizationId), path: { id: invitationId } },
    }),
  );
}

export async function revokeInvitation(
  client: ApiClient,
  organizationId: string,
  invitationId: string,
): Promise<Invitation> {
  const { data, response } = await client.POST("/api/invitations/{id}/revoke/", {
    params: { header: organizationHeader(organizationId), path: { id: invitationId } },
  });
  if (data === undefined) {
    throw await apiErrorFromResponse(response);
  }
  return data;
}

// After any answer the invitations are read again (`invitation_pending`, `invalid_transition` or
// `not_found` mean the list was stale), and the company's `allowed_actions` too:
// `organization_suspended` takes the writes away.
function useInvitationsRefresh(organizationId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: invitationsQueryKey(organizationId) }),
      queryClient.invalidateQueries({ queryKey: currentOrganizationQueryKey(organizationId) }),
    ]);
  };
}

export function useCreateInvitation(
  organizationId: string,
  onLink: OnInvitationLink,
  client: ApiClient = apiClient,
) {
  const refresh = useInvitationsRefresh(organizationId);
  return useMutation<Invitation, ApiError, InviteRequest>({
    mutationFn: async (body) =>
      handOver(await createInvitation(client, organizationId, body), onLink),
    onSettled: () => refresh(),
  });
}

export function useResendInvitation(
  organizationId: string,
  onLink: OnInvitationLink,
  client: ApiClient = apiClient,
) {
  const refresh = useInvitationsRefresh(organizationId);
  return useMutation<Invitation, ApiError, { invitationId: string }>({
    mutationFn: async ({ invitationId }) =>
      handOver(await resendInvitation(client, organizationId, invitationId), onLink),
    onSettled: () => refresh(),
  });
}

export function useRevokeInvitation(organizationId: string, client: ApiClient = apiClient) {
  const refresh = useInvitationsRefresh(organizationId);
  return useMutation<Invitation, ApiError, { invitationId: string }>({
    mutationFn: ({ invitationId }) => revokeInvitation(client, organizationId, invitationId),
    onSettled: () => refresh(),
  });
}

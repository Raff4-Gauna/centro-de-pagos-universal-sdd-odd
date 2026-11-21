"use client";

import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import {
  apiClient,
  type ApiClient,
  organizationHeader,
  orgHeaderFromKey,
  orgQueryKey,
} from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";
import type { components } from "@/types/api";

import { HOME_PATH, NO_ORGANIZATION_PATH } from "../context/ActiveOrgProvider";
import type { Role } from "../lib/role-labels";
import { currentOrganizationQueryKey } from "./useCurrentOrganizationDetails";
import { ORGANIZATIONS_PAGE_SIZE, organizationsQueryOptions } from "./useOrganizations";

// The members of the active company (RF-TEN-04, spec §14, design.md §3.9, §4.2, §6): list (active
// or ended), change a role, revoke someone else's access and leave the company. Each row brings the
// `allowed_actions` and `assignable_roles` the backend lets through now; the UI offers only those
// and the backend decides again under its lock. The list query names its company from its own
// `['org', orgId, 'members', status]` key (`orgHeaderFromKey`); a mutation names the company the
// dialog was opened for. Nothing is shown changed before the backend's `2xx`.
export type Member = components["schemas"]["OrganizationMember"];

// "Activos / Dados de baja" of the screen → `?status=`.
export const MEMBER_STATUSES = ["active", "revoked"] as const;
export type MemberStatus = (typeof MEMBER_STATUSES)[number];

export const MEMBERS_PAGE_SIZE = ORGANIZATIONS_PAGE_SIZE;

export function membersScopeKey(organizationId: string) {
  return orgQueryKey(organizationId, "members");
}

export function membersQueryKey(organizationId: string, status: MemberStatus) {
  return orgQueryKey(organizationId, "members", status);
}

type MembersQueryKey = ReturnType<typeof membersQueryKey>;

export async function fetchMembers(
  client: ApiClient,
  queryKey: MembersQueryKey,
  signal?: AbortSignal,
): Promise<Member[]> {
  const status = queryKey[3];
  const members: Member[] = [];
  for (let page = 1; ; page += 1) {
    const { data, response } = await client.GET("/api/memberships/", {
      params: {
        header: orgHeaderFromKey(queryKey),
        query: { page, page_size: MEMBERS_PAGE_SIZE, status },
      },
      signal,
    });
    if (data === undefined) {
      // A 2xx without the body of the contract: an unexpected response, never an empty list.
      throw await apiErrorFromResponse(response);
    }
    members.push(...data.results);
    // `count` bounds the loop too: a `next` that never ends cannot keep the tab reading.
    if (!data.next || data.results.length === 0 || members.length >= data.count) {
      return members;
    }
  }
}

export function membersQueryOptions(
  organizationId: string,
  status: MemberStatus,
  client: ApiClient = apiClient,
) {
  return queryOptions<Member[], ApiError, Member[], MembersQueryKey>({
    queryKey: membersQueryKey(organizationId, status),
    queryFn: ({ queryKey, signal }) => fetchMembers(client, queryKey, signal),
  });
}

// Disabled while the tab has no company yet: a request without the header is never sent.
export function useMembers(organizationId: string | null, status: MemberStatus) {
  return useQuery({
    ...membersQueryOptions(organizationId ?? "", status),
    enabled: organizationId !== null,
  });
}

// A non-2xx answer is already thrown by the api-client; a 2xx without a body is unexpected.
async function unwrap<T>(result: { data?: T; response: Response }): Promise<T> {
  if (result.data === undefined) {
    throw await apiErrorFromResponse(result.response);
  }
  return result.data;
}

export async function changeMemberRole(
  client: ApiClient,
  organizationId: string,
  membershipId: string,
  role: Role,
): Promise<Member> {
  return unwrap(
    await client.PATCH("/api/memberships/{id}/", {
      params: { header: organizationHeader(organizationId), path: { id: membershipId } },
      body: { role },
    }),
  );
}

// `204` without a body: only an answer that is not `204` is a failure the client did not throw.
async function expectNoContent(result: { response: Response }): Promise<void> {
  if (result.response.status !== 204) {
    throw await apiErrorFromResponse(result.response);
  }
}

export async function revokeMember(
  client: ApiClient,
  organizationId: string,
  membershipId: string,
): Promise<void> {
  await expectNoContent(
    await client.DELETE("/api/memberships/{id}/", {
      params: { header: organizationHeader(organizationId), path: { id: membershipId } },
    }),
  );
}

export async function leaveOrganization(client: ApiClient, organizationId: string): Promise<void> {
  await expectNoContent(
    await client.POST("/api/memberships/me/leave/", {
      params: { header: organizationHeader(organizationId) },
    }),
  );
}

// After any answer the members are read again (a `409 invalid_transition` or `last_owner` means the
// list was stale), and the company's `allowed_actions` too: a role change can be one's own, and
// `organization_suspended` takes the writes away.
function useMembersRefresh(organizationId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: membersScopeKey(organizationId) }),
      queryClient.invalidateQueries({ queryKey: currentOrganizationQueryKey(organizationId) }),
    ]);
  };
}

export function useChangeMemberRole(organizationId: string, client: ApiClient = apiClient) {
  const queryClient = useQueryClient();
  const refresh = useMembersRefresh(organizationId);
  return useMutation<Member, ApiError, { membershipId: string; role: Role }>({
    mutationFn: ({ membershipId, role }) =>
      changeMemberRole(client, organizationId, membershipId, role),
    onSettled: async (_data, error) => {
      const refreshes = [refresh()];
      if (error === null) {
        // The role of each company in the selector is the person's own: it may be this one.
        refreshes.push(
          queryClient.invalidateQueries({ queryKey: organizationsQueryOptions().queryKey }),
        );
      }
      await Promise.all(refreshes);
    },
  });
}

export function useRevokeMember(organizationId: string, client: ApiClient = apiClient) {
  const refresh = useMembersRefresh(organizationId);
  return useMutation<void, ApiError, { membershipId: string }>({
    mutationFn: ({ membershipId }) => revokeMember(client, organizationId, membershipId),
    onSettled: () => refresh(),
  });
}

// Leaving takes the company away from this tab: once the backend answered `204`, the list of the
// person's companies is read again, so the shell (ActiveOrgProvider) drops it, moves the tab to
// another one and removes the cached data of the one left; then the browser goes to "Inicio", or to
// "sin organización" when none is left. The members of the company left are not read again: that
// request would be a `404 organization_not_found`. Handled in the mutation's own options, not in a
// `mutate` callback, because the dialog unmounts as soon as the tab changes company.
export function useLeaveOrganization(organizationId: string, client: ApiClient = apiClient) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const refresh = useMembersRefresh(organizationId);
  return useMutation<void, ApiError, void>({
    mutationFn: () => leaveOrganization(client, organizationId),
    onSuccess: async () => {
      let remaining: number | null = null;
      try {
        const list = await queryClient.fetchQuery({ ...organizationsQueryOptions(), staleTime: 0 });
        remaining = list.length;
      } catch {
        // The list failed: the next request about the company left is a `404` the shell handles.
      }
      router.replace(remaining === 0 ? NO_ORGANIZATION_PATH : HOME_PATH);
    },
    onError: () => refresh(),
  });
}

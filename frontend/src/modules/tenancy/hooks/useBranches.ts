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

import { currentOrganizationQueryKey } from "./useCurrentOrganizationDetails";
import { ORGANIZATIONS_PAGE_SIZE } from "./useOrganizations";

// The branches of the active company (RF-TEN-06, spec §14, design.md §3.9, §6): list (active and
// inactive, AC-TEN-30), create, edit, deactivate and reactivate. A branch is never deleted.
// The list query names its company from its own `['org', orgId, 'branches', filter]` key
// (`orgHeaderFromKey`); a mutation names the company the screen showed when it was built, and
// rereads the branches of that same company. Only the backend's answer changes what is shown:
// a branch is shown created, edited or deactivated after the `2xx`, never before.
export type Branch = components["schemas"]["Branch"];
export type BranchCreate = components["schemas"]["BranchCreateRequest"];
export type BranchChanges = components["schemas"]["PatchedBranchUpdateRequest"];

// "Activas / Inactivas / Todas" of the screen → `?is_active=` (none: all).
export const BRANCH_FILTERS = ["all", "active", "inactive"] as const;
export type BranchFilter = (typeof BRANCH_FILTERS)[number];
const IS_ACTIVE_PARAM = { all: undefined, active: "true", inactive: "false" } as const;

// The largest page the backend allows (the same pagination as the companies).
export const BRANCHES_PAGE_SIZE = ORGANIZATIONS_PAGE_SIZE;

export function branchesScopeKey(organizationId: string) {
  return orgQueryKey(organizationId, "branches");
}

export function branchesQueryKey(organizationId: string, filter: BranchFilter) {
  return orgQueryKey(organizationId, "branches", filter);
}

type BranchesQueryKey = ReturnType<typeof branchesQueryKey>;

export async function fetchBranches(
  client: ApiClient,
  queryKey: BranchesQueryKey,
  signal?: AbortSignal,
): Promise<Branch[]> {
  const is_active = IS_ACTIVE_PARAM[queryKey[3]];
  const branches: Branch[] = [];
  for (let page = 1; ; page += 1) {
    const { data, response } = await client.GET("/api/branches/", {
      params: {
        header: orgHeaderFromKey(queryKey),
        query: { page, page_size: BRANCHES_PAGE_SIZE, ...(is_active ? { is_active } : {}) },
      },
      signal,
    });
    if (data === undefined) {
      // A 2xx without the body of the contract: an unexpected response, never an empty list.
      throw await apiErrorFromResponse(response);
    }
    branches.push(...data.results);
    // `count` bounds the loop too: a `next` that never ends cannot keep the tab reading.
    if (!data.next || data.results.length === 0 || branches.length >= data.count) {
      return branches;
    }
  }
}

export function branchesQueryOptions(
  organizationId: string,
  filter: BranchFilter,
  client: ApiClient = apiClient,
) {
  return queryOptions<Branch[], ApiError, Branch[], BranchesQueryKey>({
    queryKey: branchesQueryKey(organizationId, filter),
    queryFn: ({ queryKey, signal }) => fetchBranches(client, queryKey, signal),
  });
}

// Disabled while the tab has no company yet: a request without the header is never sent.
export function useBranches(organizationId: string | null, filter: BranchFilter) {
  return useQuery({
    ...branchesQueryOptions(organizationId ?? "", filter),
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

export async function createBranch(
  client: ApiClient,
  organizationId: string,
  body: BranchCreate,
): Promise<Branch> {
  return unwrap(
    await client.POST("/api/branches/", {
      params: { header: organizationHeader(organizationId) },
      body,
    }),
  );
}

export async function updateBranch(
  client: ApiClient,
  organizationId: string,
  branchId: string,
  body: BranchChanges,
): Promise<Branch> {
  return unwrap(
    await client.PATCH("/api/branches/{id}/", {
      params: { header: organizationHeader(organizationId), path: { id: branchId } },
      body,
    }),
  );
}

export type BranchTransition = "deactivate" | "reactivate";

export async function changeBranchState(
  client: ApiClient,
  organizationId: string,
  branchId: string,
  transition: BranchTransition,
): Promise<Branch> {
  const params = { header: organizationHeader(organizationId), path: { id: branchId } };
  return unwrap(
    transition === "deactivate"
      ? await client.POST("/api/branches/{id}/deactivate/", { params })
      : await client.POST("/api/branches/{id}/reactivate/", { params }),
  );
}

// After any answer the branches are read again (a `409 conflict` or `invalid_transition` means the
// list was stale), and on `organization_suspended` the company's `allowed_actions` too, so the
// actions the backend no longer allows disappear.
function useBranchesRefresh(organizationId: string) {
  const queryClient = useQueryClient();
  return async (error: ApiError | null) => {
    const refreshes = [
      queryClient.invalidateQueries({ queryKey: branchesScopeKey(organizationId) }),
    ];
    if (error?.code === "organization_suspended") {
      refreshes.push(
        queryClient.invalidateQueries({ queryKey: currentOrganizationQueryKey(organizationId) }),
      );
    }
    await Promise.all(refreshes);
  };
}

export function useCreateBranch(organizationId: string, client: ApiClient = apiClient) {
  const refresh = useBranchesRefresh(organizationId);
  return useMutation<Branch, ApiError, BranchCreate>({
    mutationFn: (body) => createBranch(client, organizationId, body),
    onSettled: (_data, error) => refresh(error),
  });
}

export function useUpdateBranch(organizationId: string, client: ApiClient = apiClient) {
  const refresh = useBranchesRefresh(organizationId);
  return useMutation<Branch, ApiError, { branchId: string; changes: BranchChanges }>({
    mutationFn: ({ branchId, changes }) => updateBranch(client, organizationId, branchId, changes),
    onSettled: (_data, error) => refresh(error),
  });
}

export function useChangeBranchState(organizationId: string, client: ApiClient = apiClient) {
  const refresh = useBranchesRefresh(organizationId);
  return useMutation<Branch, ApiError, { branchId: string; transition: BranchTransition }>({
    mutationFn: ({ branchId, transition }) =>
      changeBranchState(client, organizationId, branchId, transition),
    onSettled: (_data, error) => refresh(error),
  });
}

"use client";

import { queryOptions, useQuery } from "@tanstack/react-query";

import { apiClient, type ApiClient, orgHeaderFromKey, orgQueryKey } from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";
import type { components } from "@/types/api";

// The active company as `GET /api/organizations/current/` shows it (RF-TEN-03, design.md §6):
// its data, the person's role and the `allowed_actions` of SPEC-02 the backend lets through now
// (role and suspension). A screen shows an action only if it is in that list; the backend checks
// every request again (design.md §3.9). The key is the company's own `['org', orgId, 'current']`,
// so the request names the company its answer is cached under.
export type CurrentOrganizationDetails = components["schemas"]["CurrentOrganization"];
export type TenancyAction = components["schemas"]["TenancyActionEnum"];

export function currentOrganizationQueryKey(organizationId: string) {
  return orgQueryKey(organizationId, "current");
}

type CurrentOrganizationQueryKey = ReturnType<typeof currentOrganizationQueryKey>;

export async function fetchCurrentOrganization(
  client: ApiClient,
  queryKey: CurrentOrganizationQueryKey,
  signal?: AbortSignal,
): Promise<CurrentOrganizationDetails> {
  const { data, response } = await client.GET("/api/organizations/current/", {
    params: { header: orgHeaderFromKey(queryKey) },
    signal,
  });
  if (data === undefined) {
    throw await apiErrorFromResponse(response);
  }
  return data;
}

export function currentOrganizationQueryOptions(
  organizationId: string,
  client: ApiClient = apiClient,
) {
  return queryOptions<
    CurrentOrganizationDetails,
    ApiError,
    CurrentOrganizationDetails,
    CurrentOrganizationQueryKey
  >({
    queryKey: currentOrganizationQueryKey(organizationId),
    queryFn: ({ queryKey, signal }) => fetchCurrentOrganization(client, queryKey, signal),
  });
}

export function useCurrentOrganizationDetails(organizationId: string | null) {
  return useQuery({
    ...currentOrganizationQueryOptions(organizationId ?? ""),
    enabled: organizationId !== null,
  });
}

// The actions of the company the person may run now; none until the backend said which (fail
// closed: a list that did not load, or is still loading, allows nothing).
export function allowedActionsOf(
  details: CurrentOrganizationDetails | undefined,
): ReadonlySet<TenancyAction> {
  return new Set(details?.allowed_actions ?? []);
}

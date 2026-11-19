"use client";

import { queryOptions, useQuery } from "@tanstack/react-query";

import { apiClient, type ApiClient } from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";

import type { MyOrganization } from "../lib/active-organization";

// The person's companies and their role in each (RF-TEN-02, T-TEN-12): `GET /api/organizations/`,
// active memberships only, ordered by name. The route is exempt from `X-Organization-Id`, so the
// key is not under `['org', …]` and changing company keeps it. The list is paginated (SPEC-00's
// envelope): every page is read, at the largest size the backend allows, so the selector never
// hides a company.
export const ORGANIZATIONS_QUERY_KEY = ["organizations"] as const;

// `max_page_size` of HubPageNumberPagination (backend/apps/common/api/pagination.py).
export const ORGANIZATIONS_PAGE_SIZE = 200;

export async function fetchOrganizations(
  client: ApiClient = apiClient,
  signal?: AbortSignal,
): Promise<MyOrganization[]> {
  const organizations: MyOrganization[] = [];
  for (let page = 1; ; page += 1) {
    const { data, response } = await client.GET("/api/organizations/", {
      params: { query: { page, page_size: ORGANIZATIONS_PAGE_SIZE } },
      signal,
    });
    if (data === undefined) {
      // A 2xx without the body of the contract: an unexpected response, never an empty list.
      throw await apiErrorFromResponse(response);
    }
    organizations.push(...data.results);
    // `count` bounds the loop too: a `next` that never ends cannot keep the tab reading.
    if (!data.next || data.results.length === 0 || organizations.length >= data.count) {
      return organizations;
    }
  }
}

export function organizationsQueryOptions(client: ApiClient = apiClient) {
  return queryOptions<MyOrganization[], ApiError>({
    queryKey: ORGANIZATIONS_QUERY_KEY,
    queryFn: ({ signal }) => fetchOrganizations(client, signal),
  });
}

export function useOrganizations() {
  return useQuery(organizationsQueryOptions());
}

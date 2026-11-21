"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient, type ApiClient, organizationHeader } from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";
import type { components } from "@/types/api";

import {
  type CurrentOrganizationDetails,
  currentOrganizationQueryKey,
} from "./useCurrentOrganizationDetails";
import { ORGANIZATIONS_QUERY_KEY } from "./useOrganizations";

// Editing the data of the active company (RF-TEN-03, design.md §6): `PATCH
// /api/organizations/current/` with only the fields that changed. The mutation names the company
// the form was opened for, never the one the tab shows by the time it answers. The backend answers
// the company as it is now: that body becomes the cached `['org', orgId, 'current']`, and the list
// of companies is read again because the selector shows the name. Nothing is shown saved before the
// `2xx`. A refusal that may mean the actions changed (`organization_suspended`, `403`) rereads the
// company, so the form gives way to the read-only view if the backend no longer allows editing.
export type OrganizationChanges = components["schemas"]["PatchedOrganizationUpdateRequest"];

export async function updateOrganization(
  client: ApiClient,
  organizationId: string,
  body: OrganizationChanges,
): Promise<CurrentOrganizationDetails> {
  const { data, response } = await client.PATCH("/api/organizations/current/", {
    params: { header: organizationHeader(organizationId) },
    body,
  });
  if (data === undefined) {
    // A non-2xx answer is already thrown by the api-client; a 2xx without a body is unexpected.
    throw await apiErrorFromResponse(response);
  }
  return data;
}

export function useUpdateOrganization(organizationId: string, client: ApiClient = apiClient) {
  const queryClient = useQueryClient();
  return useMutation<CurrentOrganizationDetails, ApiError, OrganizationChanges>({
    mutationFn: (body) => updateOrganization(client, organizationId, body),
    onSuccess: (data) => {
      queryClient.setQueryData(currentOrganizationQueryKey(organizationId), data);
      void queryClient.invalidateQueries({ queryKey: ORGANIZATIONS_QUERY_KEY });
    },
    onError: async (error) => {
      if (error.code === "organization_suspended" || error.status === 403) {
        await queryClient.invalidateQueries({
          queryKey: currentOrganizationQueryKey(organizationId),
        });
      }
    },
  });
}

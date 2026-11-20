import { vi } from "vitest";

import type { ApiError } from "@/lib/problem";

import type { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { useOrganizations } from "../hooks/useOrganizations";
import type { MyOrganization } from "../lib/active-organization";

// Shapes of the tenancy hooks for the component tests, which mock them: only the fields read.
export const ACME: MyOrganization = {
  id: "6a1f0c2e-1b3d-4e5f-8a9b-0c1d2e3f4a5b",
  name: "Acme",
  status: "active",
  role: "owner",
};

export const BETA: MyOrganization = {
  id: "7b2e1d3f-2c4e-4f60-9bac-1d2e3f4a5b6c",
  name: "Beta",
  status: "suspended",
  role: "viewer",
};

type OrganizationsState = Partial<{
  data: MyOrganization[];
  isPending: boolean;
  isError: boolean;
  isFetching: boolean;
  error: ApiError | null;
}>;

export function organizationsResult(state: OrganizationsState) {
  return {
    data: undefined,
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...state,
  } as unknown as ReturnType<typeof useOrganizations>;
}

export function activeOrganizationResult(
  organizationId: string | null,
): ReturnType<typeof useActiveOrganization> {
  return { organizationId, selectOrganization: vi.fn() };
}

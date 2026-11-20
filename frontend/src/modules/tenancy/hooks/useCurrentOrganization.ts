"use client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { MyOrganization } from "../lib/active-organization";
import { useOrganizations } from "./useOrganizations";

// The company this tab shows, with the person's role and the company's status (RF-TEN-02). It is
// read from `GET /api/organizations/`, the list the selector already holds: the shell needs only
// name, role and `active`/`suspended`. The company's own data and `allowed_actions` come from
// `GET /api/organizations/current/` (T-TEN-13), for the screens that need them.
export type CurrentOrganization = Readonly<{
  organization: MyOrganization | null;
  isSuspended: boolean;
}>;

export function useCurrentOrganization(): CurrentOrganization {
  const { organizationId } = useActiveOrganization();
  const organizations = useOrganizations();
  const organization =
    organizationId === null
      ? null
      : (organizations.data?.find(({ id }) => id === organizationId) ?? null);
  return { organization, isSuspended: organization?.status === "suspended" };
}

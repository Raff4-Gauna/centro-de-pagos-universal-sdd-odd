import type { Metadata } from "next";
import { connection } from "next/server";

import { getOperatorContact } from "@/lib/server/env";
import { NoOrganizationState } from "@/modules/identity/components/NoOrganizationState";
import { PendingInvitationsNotice } from "@/modules/tenancy/components/PendingInvitationsNotice";

export const metadata: Metadata = { title: "Sin organización | Centro de Pagos Universal" };

// "Sin organización" (AC-IDA-30, Q-109, Q-205, Q-124, SPEC-02 design.md §3.9): where
// ActiveOrgProvider sends a person without memberships. The operator's contact is a server
// variable (Q-050), read on every request (`connection()`: never frozen into the build) and passed
// down by prop; without a value no contact is shown. Next to it, the person's pending invitations,
// which can be accepted from here.
export default async function NoOrganizationPage() {
  await connection();
  return (
    <NoOrganizationState operatorContact={getOperatorContact()}>
      <PendingInvitationsNotice />
    </NoOrganizationState>
  );
}

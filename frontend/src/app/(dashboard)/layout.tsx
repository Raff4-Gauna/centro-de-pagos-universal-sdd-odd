import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { COOKIE_NAMES } from "@/lib/server/cookies";
import { ActiveOrgProvider } from "@/modules/tenancy/context/ActiveOrgProvider";
import { isOrganizationId } from "@/modules/tenancy/lib/active-organization";

// Layout of the authenticated area (07 §5, design.md §3.3.2). It reads, on the server, the last
// company the person picked (`__Host-cpu_org`, `HttpOnly`, ADR-0004 §7) and hands it to the tab as
// the default (Q-119 b, Q-205); a value that is not a UUID counts as absent. Only a preference:
// Django revalidates the membership on every request (RN-TEN-03).
export default async function DashboardLayout({ children }: Readonly<{ children: ReactNode }>) {
  const saved = (await cookies()).get(COOKIE_NAMES.organization)?.value;
  const defaultOrganizationId = isOrganizationId(saved) ? saved.toLowerCase() : null;
  return (
    <ActiveOrgProvider defaultOrganizationId={defaultOrganizationId}>
      <AppShell>{children}</AppShell>
    </ActiveOrgProvider>
  );
}

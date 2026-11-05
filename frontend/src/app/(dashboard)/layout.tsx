import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";

// Layout of the authenticated area (07 §5, design.md §3.3.2). Route protection arrives with SPEC-01.
export default function DashboardLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <AppShell>{children}</AppShell>;
}

"use client";

import Alert from "@mui/material/Alert";

import { useCurrentOrganization } from "../hooks/useCurrentOrganization";

// "Organización suspendida (solo lectura)" (spec §14, Q-208, design.md §3.9): shown above every page
// of the shell while the company this tab shows is `suspended`. It only informs: the backend is the
// one that refuses each write with `409 organization_suspended` (RN-TEN-18, §4.1).
export const SUSPENDED_TEXT = "Organización suspendida (solo lectura)";

export function SuspendedBanner() {
  const { isSuspended } = useCurrentOrganization();
  if (!isSuspended) {
    return null;
  }
  return (
    <Alert severity="warning" className="tw-mb-4">
      {SUSPENDED_TEXT}
    </Alert>
  );
}

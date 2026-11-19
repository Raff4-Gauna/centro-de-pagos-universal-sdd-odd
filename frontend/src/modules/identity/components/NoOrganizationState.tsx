"use client";

import Button from "@mui/material/Button";

import { EmptyState } from "@/components/EmptyState";

import { useLogout } from "../hooks/useLogout";
import { LOGOUT_LABEL, LogoutErrorAlert } from "./UserMenu";

// "Sin empresas" (AC-IDA-30, RN-IDA-22, Q-109, spec §14, design.md §3.4): a person without active
// memberships is signed in, sees this state and can only log out. Which route shows it, and the
// operator contact and pending invitations next to it, belong to SPEC-02 (T-TEN-29, T-TEN-30).
export const NO_ORGANIZATION_TITLE = "No pertenecés a ninguna empresa";

export function NoOrganizationState() {
  const logout = useLogout();
  const leaving = logout.isPending || logout.isSuccess;
  return (
    <div className="tw-flex tw-flex-col tw-items-center tw-gap-4">
      <EmptyState
        title={NO_ORGANIZATION_TITLE}
        action={
          <Button variant="contained" loading={leaving} onClick={() => logout.mutate()}>
            {LOGOUT_LABEL}
          </Button>
        }
      />
      {logout.isError ? (
        <LogoutErrorAlert
          error={logout.error}
          onRetry={() => logout.mutate()}
          retrying={logout.isPending}
        />
      ) : null}
    </div>
  );
}

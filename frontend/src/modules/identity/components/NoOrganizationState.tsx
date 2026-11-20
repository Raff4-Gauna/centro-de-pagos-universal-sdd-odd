"use client";

import Button from "@mui/material/Button";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";

import { useLogout } from "../hooks/useLogout";
import { LOGOUT_LABEL, LogoutErrorAlert } from "./UserMenu";

// "Sin empresas" (AC-IDA-30, RN-IDA-22, Q-109, spec §14, design.md §3.4): a person without active
// memberships is signed in, sees this state and can only log out. SPEC-02 mounts it on
// `/sin-organizacion` (design.md §3.9, Q-205) with the platform operator's contact, when the server
// has one (`OPERATOR_CONTACT`, plain text), and its pending invitations as `children` (Q-124).
export const NO_ORGANIZATION_TITLE = "No pertenecés a ninguna empresa";
export const OPERATOR_CONTACT_LABEL = "Contacto del operador";

export type NoOrganizationStateProps = Readonly<{
  operatorContact?: string | null;
  children?: ReactNode;
}>;

export function NoOrganizationState({
  operatorContact = null,
  children,
}: NoOrganizationStateProps) {
  const logout = useLogout();
  const leaving = logout.isPending || logout.isSuccess;
  return (
    <div className="tw-flex tw-flex-col tw-items-center tw-gap-4">
      <EmptyState
        title={NO_ORGANIZATION_TITLE}
        description={operatorContact ? `${OPERATOR_CONTACT_LABEL}: ${operatorContact}` : undefined}
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
      {children ? <div className="tw-w-full tw-max-w-3xl">{children}</div> : null}
    </div>
  );
}

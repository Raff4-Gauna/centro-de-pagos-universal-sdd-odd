"use client";

import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import { useId } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorNotice } from "@/components/ErrorNotice";
import { formatDateTime } from "@/modules/identity/lib/format-dates";

import { type Invitation, useInvitations } from "../hooks/useInvitations";
import { roleLabel } from "../lib/role-labels";
import type { InvitationWrite } from "./InvitationDialogs";

// Configuración → Colaboradores, "Invitaciones pendientes" (RF-TEN-05, spec §14, design.md §3.9):
// the pending, still valid invitations of the active company with their email, role (Q-232
// labels), who invited and until when. Only owner and admin list them (Q-218): anyone else gets
// `403` and the tab says so (AC-TEN-34). The list never carries a token (AC-TEN-24). Each row
// offers only what its own `allowed_actions` bring ("Reenviar", "Revocar"): the UI hides, the
// backend decides. States: loading (skeleton rows), error ("Reintentar"), no permission (`403`),
// empty.
export const INVITATIONS_TEXTS = {
  email: "Email",
  role: "Rol",
  invitedBy: "Invitó",
  expires: "Vence",
  actions: "Acciones",
  resend: "Reenviar",
  revoke: "Revocar",
  missing: "—",
  loading: "Cargando invitaciones",
  empty: "No hay invitaciones pendientes",
  forbidden: "No tenés permiso para ver las invitaciones",
} as const;

export const INVITATIONS_SKELETON_ROWS = 5;

export type OpenInvitation = Readonly<{ kind: InvitationWrite; invitation: Invitation }>;

function inviterOf({ invited_by }: Invitation): string {
  return invited_by?.name || invited_by?.email || INVITATIONS_TEXTS.missing;
}

function InvitationRow({
  invitation,
  hasActions,
  onOpen,
}: Readonly<{
  invitation: Invitation;
  hasActions: boolean;
  onOpen: (action: OpenInvitation) => void;
}>) {
  // The action buttons repeat their label on every row: the email cell describes each one.
  const emailId = useId();
  const allowed = new Set(invitation.allowed_actions);
  const button = (kind: InvitationWrite, label: string, danger: boolean) => (
    <Button
      size="small"
      color={danger ? "error" : "primary"}
      aria-describedby={emailId}
      onClick={() => onOpen({ kind, invitation })}
    >
      {label}
    </Button>
  );
  return (
    <TableRow>
      <TableCell id={emailId}>{invitation.email}</TableCell>
      <TableCell>
        <Chip size="small" variant="outlined" label={roleLabel(invitation.role)} />
      </TableCell>
      <TableCell>{inviterOf(invitation)}</TableCell>
      <TableCell>{formatDateTime(invitation.expires_at)}</TableCell>
      {hasActions ? (
        <TableCell align="right" className="tw-whitespace-nowrap">
          {allowed.has("invitation.resend")
            ? button("resend", INVITATIONS_TEXTS.resend, false)
            : null}
          {allowed.has("invitation.revoke")
            ? button("revoke", INVITATIONS_TEXTS.revoke, true)
            : null}
        </TableCell>
      ) : null}
    </TableRow>
  );
}

export function InvitationsTable({
  invitations,
  onOpen,
}: Readonly<{ invitations: readonly Invitation[]; onOpen: (action: OpenInvitation) => void }>) {
  const hasActions = invitations.some(({ allowed_actions }) =>
    allowed_actions.some(
      (action) => action === "invitation.resend" || action === "invitation.revoke",
    ),
  );
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{INVITATIONS_TEXTS.email}</TableCell>
            <TableCell>{INVITATIONS_TEXTS.role}</TableCell>
            <TableCell>{INVITATIONS_TEXTS.invitedBy}</TableCell>
            <TableCell>{INVITATIONS_TEXTS.expires}</TableCell>
            {hasActions ? (
              <TableCell align="right">
                <span className="tw-sr-only">{INVITATIONS_TEXTS.actions}</span>
              </TableCell>
            ) : null}
          </TableRow>
        </TableHead>
        <TableBody>
          {invitations.map((invitation) => (
            <InvitationRow
              key={invitation.id}
              invitation={invitation}
              hasActions={hasActions}
              onOpen={onOpen}
            />
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function InvitationsSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={INVITATIONS_TEXTS.loading}
      className="tw-flex tw-flex-col tw-gap-2"
    >
      <Skeleton variant="rectangular" height={56} data-skeleton="header" />
      {Array.from({ length: INVITATIONS_SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} variant="rectangular" height={52} data-skeleton="row" />
      ))}
    </div>
  );
}

export function InvitationsBody({
  organizationId,
  onOpen,
}: Readonly<{ organizationId: string | null; onOpen: (action: OpenInvitation) => void }>) {
  const invitations = useInvitations(organizationId);
  if (invitations.isPending) {
    return <InvitationsSkeleton />;
  }
  if (invitations.isError) {
    return invitations.error.status === 403 ? (
      <EmptyState title={INVITATIONS_TEXTS.forbidden} />
    ) : (
      <ErrorNotice
        message={invitations.error.title}
        onRetry={() => void invitations.refetch()}
        retrying={invitations.isFetching}
      />
    );
  }
  if (invitations.data.length === 0) {
    return <EmptyState title={INVITATIONS_TEXTS.empty} />;
  }
  return <InvitationsTable invitations={invitations.data} onOpen={onOpen} />;
}

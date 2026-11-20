"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { type ReactNode, useId, useState } from "react";

import { ErrorNotice, RETRY_LABEL } from "@/components/ErrorNotice";
import type { ApiError } from "@/lib/problem";
import { formatDateTime } from "@/modules/identity/lib/format-dates";

import { HOME_PATH, useActiveOrganization } from "../context/ActiveOrgProvider";
import {
  type AcceptedInvitation,
  type MyInvitation,
  useAcceptMyInvitation,
  useMyInvitations,
} from "../hooks/useMyInvitations";

// "Invitaciones pendientes en la sesión" (spec §14, RN-TEN-11, AC-TEN-39, Q-121, Q-124, design.md
// §3.9): on "Inicio" and on "sin organización", each pending invitation of the person's email with
// company, role and expiry, and "Aceptar". Without invitations nothing is shown. An invitation is
// shown as accepted only after the backend's `200`: then its row offers "Ir a la empresa", which
// picks that company for this tab. A refused accept shows the fixed title of its code
// (`ApiError.title`, never `detail`, C-08); only a network or server failure offers "Reintentar".
// Texts: the words of spec §14 and design.md §3.9; the role is the code of 07 §5.3.
export const PENDING_INVITATIONS_TEXTS = {
  title: "Invitaciones pendientes",
  organization: "Empresa",
  role: "Rol",
  expires: "Vencimiento",
  accept: "Aceptar",
  goToOrganization: "Ir a la empresa",
  loading: "Cargando",
} as const;

type AcceptFailure = Readonly<{ invitationId: string; error: ApiError }>;

function isRetryable(error: ApiError): boolean {
  return error.status === 0 || error.status >= 500;
}

function NoticeFrame({ titleId, children }: Readonly<{ titleId: string; children: ReactNode }>) {
  return (
    <Paper component="section" variant="outlined" aria-labelledby={titleId} className="tw-p-4">
      <Typography id={titleId} component="h2" variant="h6" className="tw-mb-2">
        {PENDING_INVITATIONS_TEXTS.title}
      </Typography>
      {children}
    </Paper>
  );
}

function NoticeSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={PENDING_INVITATIONS_TEXTS.loading}
      className="tw-flex tw-flex-col tw-gap-2"
    >
      <Skeleton variant="text" width="30%" height={32} data-skeleton="title" />
      <Skeleton variant="rectangular" height={52} data-skeleton="row" />
    </div>
  );
}

type RowProps = Readonly<{
  invitation: MyInvitation;
  accepted: AcceptedInvitation | undefined;
  accepting: boolean;
  busy: boolean;
  onAccept: () => void;
  onGoTo: (organizationId: string) => void;
}>;

function InvitationRow({ invitation, accepted, accepting, busy, onAccept, onGoTo }: RowProps) {
  // The buttons repeat their label on every row: the company cell describes each one.
  const companyId = useId();
  return (
    <TableRow>
      <TableCell>
        <span id={companyId}>{invitation.organization.name}</span>
      </TableCell>
      <TableCell>{invitation.role}</TableCell>
      <TableCell>{formatDateTime(invitation.expires_at)}</TableCell>
      <TableCell align="right">
        {accepted ? (
          <Button
            size="small"
            variant="contained"
            aria-describedby={companyId}
            onClick={() => onGoTo(accepted.organization.id)}
          >
            {PENDING_INVITATIONS_TEXTS.goToOrganization}
          </Button>
        ) : (
          <Button
            size="small"
            variant="contained"
            aria-describedby={companyId}
            loading={accepting}
            disabled={busy && !accepting}
            onClick={onAccept}
          >
            {PENDING_INVITATIONS_TEXTS.accept}
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

export function PendingInvitationsNotice() {
  const titleId = useId();
  const router = useRouter();
  const { selectOrganization } = useActiveOrganization();
  const invitations = useMyInvitations();
  const accept = useAcceptMyInvitation();
  // Accepted in this visit: the list is read again after an accept and no longer brings them, but
  // their row stays, with "Ir a la empresa", until the person leaves the screen.
  const [accepted, setAccepted] = useState<
    ReadonlyArray<Readonly<{ invitation: MyInvitation; result: AcceptedInvitation }>>
  >([]);
  const [failure, setFailure] = useState<AcceptFailure | null>(null);

  function acceptInvitation(invitation: MyInvitation) {
    setFailure(null);
    accept.mutate(invitation.id, {
      onSuccess: (result) => setAccepted((done) => [...done, { invitation, result }]),
      onError: (error) => setFailure({ invitationId: invitation.id, error }),
    });
  }

  function goTo(organizationId: string) {
    selectOrganization(organizationId);
    router.push(HOME_PATH);
  }

  if (invitations.isPending) {
    return <NoticeSkeleton />;
  }
  if (invitations.isError) {
    return (
      <NoticeFrame titleId={titleId}>
        <ErrorNotice
          message={invitations.error.title}
          onRetry={() => void invitations.refetch()}
          retrying={invitations.isFetching}
        />
      </NoticeFrame>
    );
  }

  const acceptedIds = new Set(accepted.map(({ invitation }) => invitation.id));
  const rows = [
    ...invitations.data
      .filter(({ id }) => !acceptedIds.has(id))
      .map((invitation) => ({ invitation, result: undefined })),
    ...accepted,
  ];
  if (rows.length === 0) {
    return null; // Without invitations the notice is not shown (design.md §3.9).
  }
  const pendingId = accept.isPending ? accept.variables : undefined;
  const byId = new Map(rows.map(({ invitation }) => [invitation.id, invitation]));
  const retryTarget = failure ? byId.get(failure.invitationId) : undefined;

  return (
    <NoticeFrame titleId={titleId}>
      {failure ? (
        <Alert
          severity="error"
          className="tw-mb-2"
          action={
            isRetryable(failure.error) && retryTarget ? (
              <Button color="inherit" size="small" onClick={() => acceptInvitation(retryTarget)}>
                {RETRY_LABEL}
              </Button>
            ) : undefined
          }
        >
          {failure.error.title}
        </Alert>
      ) : null}
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{PENDING_INVITATIONS_TEXTS.organization}</TableCell>
            <TableCell>{PENDING_INVITATIONS_TEXTS.role}</TableCell>
            <TableCell>{PENDING_INVITATIONS_TEXTS.expires}</TableCell>
            <TableCell align="right">
              <span className="tw-sr-only">{PENDING_INVITATIONS_TEXTS.accept}</span>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map(({ invitation, result }) => (
            // A React key, never rendered: the invitation id does not reach the DOM.
            <InvitationRow
              key={invitation.id}
              invitation={invitation}
              accepted={result}
              accepting={pendingId === invitation.id}
              busy={accept.isPending}
              onAccept={() => acceptInvitation(invitation)}
              onGoTo={goTo}
            />
          ))}
        </TableBody>
      </Table>
    </NoticeFrame>
  );
}

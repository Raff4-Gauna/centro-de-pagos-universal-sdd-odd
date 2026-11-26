"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import { useId, useState } from "react";

import type { ApiError } from "@/lib/problem";

import {
  type Invitation,
  type InvitationLink,
  useResendInvitation,
  useRevokeInvitation,
} from "../hooks/useInvitations";
import { invitationErrorText } from "../lib/invitation-errors";
import { InvitationLinkDialog } from "./InvitationLinkDialog";

// Confirmation of the two writes on a pending invitation (RF-TEN-05, RN-TEN-12, Q-206, design.md
// §4.3): "Reenviar" (`POST /api/invitations/{id}/resend/`, `invitation.resend`) voids the link and
// issues a new one with a new expiry; "Revocar" (`POST /api/invitations/{id}/revoke/`,
// `invitation.revoke`) voids it, also with the company suspended (Q-221: the backend says so by
// bringing the action). While the request runs nothing else can be pressed and the dialog does
// not close. A refusal stays inside it (`409 invalid_transition`, `404`, `403`,
// `organization_suspended`, `503 organization_busy`) and the list is read again. After the
// backend's answer, revoking closes the dialog; resending gives way to the new link, shown once
// (InvitationLinkDialog) and kept only in this dialog's state (AC-TEN-24).
export type InvitationWrite = "resend" | "revoke";

export const INVITATION_DIALOG_TEXTS = {
  resend: {
    title: (email: string) => `¿Reenviar la invitación a ${email}?`,
    body: "Se genera un link nuevo, con un vencimiento nuevo, y el anterior deja de funcionar. El link nuevo se muestra una sola vez.",
    confirm: "Reenviar",
  },
  revoke: {
    title: (email: string) => `¿Revocar la invitación a ${email}?`,
    body: "El link deja de funcionar. Para sumar a esa persona después hace falta una invitación nueva.",
    confirm: "Revocar",
  },
  cancel: "Cancelar",
} as const;

export type InvitationDialogProps = Readonly<{
  organizationId: string;
  invitation: Invitation;
  onClose: () => void;
}>;

function ConfirmDialog({
  kind,
  invitation,
  busy,
  error,
  onConfirm,
  onClose,
}: Readonly<{
  kind: InvitationWrite;
  invitation: Invitation;
  busy: boolean;
  error: ApiError | null;
  onConfirm: () => void;
  onClose: () => void;
}>) {
  const titleId = useId();
  const bodyId = useId();
  const texts = INVITATION_DIALOG_TEXTS[kind];
  return (
    <Dialog
      open
      onClose={busy ? undefined : onClose}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
    >
      <DialogTitle id={titleId}>{texts.title(invitation.email)}</DialogTitle>
      <DialogContent className="tw-flex tw-flex-col tw-gap-4">
        <DialogContentText id={bodyId}>{texts.body}</DialogContentText>
        {error !== null ? <Alert severity="error">{invitationErrorText(error)}</Alert> : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          {INVITATION_DIALOG_TEXTS.cancel}
        </Button>
        <Button
          variant="contained"
          color={kind === "revoke" ? "error" : "primary"}
          loading={busy}
          onClick={onConfirm}
        >
          {texts.confirm}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ResendConfirm({
  organizationId,
  invitation,
  onClose,
  onLink,
}: InvitationDialogProps & Readonly<{ onLink: (link: InvitationLink) => void }>) {
  const resend = useResendInvitation(organizationId, onLink);
  return (
    <ConfirmDialog
      kind="resend"
      invitation={invitation}
      busy={resend.isPending}
      error={resend.error}
      onConfirm={() => resend.mutate({ invitationId: invitation.id })}
      onClose={onClose}
    />
  );
}

export function ResendInvitationDialog(props: InvitationDialogProps) {
  const [link, setLink] = useState<InvitationLink | null>(null);
  if (link !== null) {
    return <InvitationLinkDialog link={link} onClose={props.onClose} />;
  }
  return <ResendConfirm {...props} onLink={setLink} />;
}

export function RevokeInvitationDialog({
  organizationId,
  invitation,
  onClose,
}: InvitationDialogProps) {
  const revoke = useRevokeInvitation(organizationId);
  return (
    <ConfirmDialog
      kind="revoke"
      invitation={invitation}
      busy={revoke.isPending}
      error={revoke.error}
      onConfirm={() => revoke.mutate({ invitationId: invitation.id }, { onSuccess: onClose })}
      onClose={onClose}
    />
  );
}

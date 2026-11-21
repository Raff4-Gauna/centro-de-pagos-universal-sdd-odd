"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import { useId } from "react";

import type { ApiError } from "@/lib/problem";

import { type Member, useLeaveOrganization, useRevokeMember } from "../hooks/useMembers";
import { memberErrorText } from "../lib/member-errors";
import { memberDisplayName } from "./MemberRoleDialog";

// Confirmation of the two ways a membership ends (RF-TEN-04, RN-TEN-21, design.md §4.2): "Revocar
// acceso" on someone else's row (`DELETE /api/memberships/{id}/`, `member.revoke`) and "Abandonar
// la empresa" on one's own (`POST /api/memberships/me/leave/`, `member.leave`). Both go on with the
// company suspended (Q-221): the backend says so by bringing the action. While the request runs
// nothing else can be pressed and the dialog does not close. A refusal stays inside it (`409
// last_owner` explained, `503 organization_busy`, `invalid_transition`) and the list is read
// again. After the `204`, revoking closes the dialog; leaving sends the tab away (useMembers).
// Leaving is about the person, not a row: "Datos de la empresa" opens the same dialog (T-TEN-32).
export type MemberExit = "revoke" | "leave";

export const MEMBER_EXIT_TEXTS = {
  revoke: {
    title: (name: string) => `¿Revocar el acceso de ${name}?`,
    body: "Deja de ver la empresa y queda en la lista de dados de baja. Para volver necesita una invitación nueva.",
    confirm: "Revocar acceso",
  },
  leave: {
    title: () => "¿Abandonar la empresa?",
    body: "Dejás de ver esta empresa. Para volver necesitás una invitación nueva.",
    confirm: "Abandonar",
  },
  cancel: "Cancelar",
} as const;

type Exit = Readonly<{
  run: (onDone: () => void) => void;
  isPending: boolean;
  error: ApiError | null;
}>;

function useRevoke(organizationId: string, member: Member): Exit {
  const revoke = useRevokeMember(organizationId);
  return {
    run: (onDone) => revoke.mutate({ membershipId: member.id }, { onSuccess: onDone }),
    isPending: revoke.isPending,
    error: revoke.error,
  };
}

function useLeave(organizationId: string): Exit {
  const leave = useLeaveOrganization(organizationId);
  // Leaving never closes by itself: the tab moves to another company and the screen goes with it.
  return { run: () => leave.mutate(), isPending: leave.isPending, error: leave.error };
}

export type MemberExitDialogProps = Readonly<{
  organizationId: string;
  member: Member;
  onClose: () => void;
}>;

function ExitDialog({
  title,
  exit,
  kind,
  onClose,
}: Readonly<{ title: string; exit: Exit; kind: MemberExit; onClose: () => void }>) {
  const titleId = useId();
  const bodyId = useId();
  const texts = MEMBER_EXIT_TEXTS[kind];
  const busy = exit.isPending;
  return (
    <Dialog
      open
      onClose={busy ? undefined : onClose}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      <DialogContent className="tw-flex tw-flex-col tw-gap-4">
        <DialogContentText id={bodyId}>{texts.body}</DialogContentText>
        {exit.error !== null ? <Alert severity="error">{memberErrorText(exit.error)}</Alert> : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          {MEMBER_EXIT_TEXTS.cancel}
        </Button>
        <Button variant="contained" color="error" loading={busy} onClick={() => exit.run(onClose)}>
          {texts.confirm}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function RevokeMemberDialog({ organizationId, member, onClose }: MemberExitDialogProps) {
  const exit = useRevoke(organizationId, member);
  const title = MEMBER_EXIT_TEXTS.revoke.title(memberDisplayName(member));
  return <ExitDialog title={title} exit={exit} kind="revoke" onClose={onClose} />;
}

export function LeaveOrganizationDialog({
  organizationId,
  onClose,
}: Omit<MemberExitDialogProps, "member">) {
  const exit = useLeave(organizationId);
  const title = MEMBER_EXIT_TEXTS.leave.title();
  return <ExitDialog title={title} exit={exit} kind="leave" onClose={onClose} />;
}

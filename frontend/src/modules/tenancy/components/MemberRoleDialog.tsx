"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useId, useState } from "react";

import { type Member, useChangeMemberRole } from "../hooks/useMembers";
import { memberErrorText } from "../lib/member-errors";
import { type Role, roleLabel } from "../lib/role-labels";

// "Cambiar rol" of a member (RF-TEN-04, design.md §4.2): the roles offered are exactly the row's
// `assignable_roles` (never the current one; the backend computed them with the role rules), shown
// with their labels (Q-232). It starts with no role picked, so confirming is always a choice. While
// the request runs nothing else can be pressed and the dialog does not close; it closes only after
// the backend's `200`. A refusal (`409 last_owner`, `503 organization_busy`, `invalid_transition`,
// `organization_suspended`, `403`) stays inside it and the list is read again (useMembers).
export const MEMBER_ROLE_TEXTS = {
  title: (name: string) => `Cambiar el rol de ${name}`,
  current: (role: string) => `Rol actual: ${role}.`,
  newRole: "Nuevo rol",
  confirm: "Cambiar rol",
  cancel: "Cancelar",
} as const;

export function memberDisplayName(member: Member): string {
  return member.user.name || member.user.email;
}

export type MemberRoleDialogProps = Readonly<{
  organizationId: string;
  member: Member;
  onClose: () => void;
}>;

export function MemberRoleDialog({ organizationId, member, onClose }: MemberRoleDialogProps) {
  const titleId = useId();
  const bodyId = useId();
  const change = useChangeMemberRole(organizationId);
  const [role, setRole] = useState<Role | "">("");
  const busy = change.isPending;
  const roles = member.assignable_roles;
  return (
    <Dialog
      open
      onClose={busy ? undefined : onClose}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      fullWidth
      maxWidth="xs"
    >
      <DialogTitle id={titleId}>{MEMBER_ROLE_TEXTS.title(memberDisplayName(member))}</DialogTitle>
      <DialogContent className="tw-flex tw-flex-col tw-gap-4">
        <DialogContentText id={bodyId}>
          {MEMBER_ROLE_TEXTS.current(roleLabel(member.role))}
        </DialogContentText>
        <TextField
          select
          label={MEMBER_ROLE_TEXTS.newRole}
          value={role}
          disabled={busy}
          onChange={(event) => setRole(event.target.value as Role)}
          className="tw-mt-2"
        >
          {roles.map((value) => (
            <MenuItem key={value} value={value}>
              {roleLabel(value)}
            </MenuItem>
          ))}
        </TextField>
        {change.isError ? <Alert severity="error">{memberErrorText(change.error)}</Alert> : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          {MEMBER_ROLE_TEXTS.cancel}
        </Button>
        <Button
          variant="contained"
          loading={busy}
          disabled={role === "" || !roles.includes(role)}
          onClick={() => {
            if (role !== "") {
              change.mutate({ membershipId: member.id, role }, { onSuccess: onClose });
            }
          }}
        >
          {MEMBER_ROLE_TEXTS.confirm}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

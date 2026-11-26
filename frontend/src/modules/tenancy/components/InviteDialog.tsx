"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useId, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";

import type { ApiError } from "@/lib/problem";

import { type InvitationLink, useCreateInvitation } from "../hooks/useInvitations";
import { invitationErrorText } from "../lib/invitation-errors";
import {
  EMPTY_INVITE,
  INVITE_FIELDS,
  type InviteFieldErrors,
  inviteFieldErrorsFrom,
  type InviteRequest,
  inviteResolver,
  type InviteValues,
} from "../lib/invite-form";
import { type Role, roleLabel } from "../lib/role-labels";
import { InvitationLinkDialog } from "./InvitationLinkDialog";

// "Invitar" (RF-TEN-05, AC-TEN-24, design.md §3.9, §4.3): email and role, with react-hook-form and
// the zod schema of lib/invite-form.ts (07 §3.3, Q-239). The roles offered are exactly the
// company's `invitable_roles` (the backend computed them for the person: an admin gets no Dueño),
// with their labels (Q-232), and none is picked at first. While the request runs nothing else can
// be pressed and the dialog does not close. A refusal stays inside it and the list is read again:
// - `400 validation_error`: each message goes under its field;
// - `409 already_member` / `invitation_pending`, `403`, `409 organization_suspended`,
//   `503 organization_busy` (Q-230) and the rest: the text of lib/invitation-errors.ts above.
// After the backend's `201` the form gives way to the link, shown once (InvitationLinkDialog). The
// link lives in this component's state and nowhere else (AC-TEN-24): closing unmounts the dialog
// and it is gone, and the screen of another company never has it (`key` per company).
export const INVITE_TEXTS = {
  title: "Invitar a la empresa",
  email: "Email",
  role: "Rol",
  emailHelp: "El de la cuenta de Google con la que va a ingresar.",
  confirm: "Invitar",
  cancel: "Cancelar",
} as const;

// The message above the fields: the field errors already sit under their field.
function formErrorText(error: ApiError, fieldErrors: InviteFieldErrors): string | null {
  if (error.code === "validation_error" && Object.keys(fieldErrors).length > 0) {
    return null;
  }
  return invitationErrorText(error);
}

export type InviteDialogProps = Readonly<{
  organizationId: string;
  invitableRoles: readonly Role[];
  onClose: () => void;
}>;

function InviteForm({
  organizationId,
  invitableRoles,
  onClose,
  onLink,
}: InviteDialogProps & Readonly<{ onLink: (link: InvitationLink) => void }>) {
  const titleId = useId();
  const create = useCreateInvitation(organizationId, onLink);
  const resolver = useMemo(() => inviteResolver(invitableRoles), [invitableRoles]);
  const { control, handleSubmit, setError } = useForm<InviteValues, unknown, InviteRequest>({
    defaultValues: EMPTY_INVITE,
    resolver,
  });
  const busy = create.isPending;
  const serverError = create.isError ? create.error : null;
  const formError = serverError
    ? formErrorText(serverError, inviteFieldErrorsFrom(serverError.fieldErrors))
    : null;

  const onSubmit = handleSubmit((values) => {
    create.mutate(values, {
      onError: (error) => {
        const fieldErrors = inviteFieldErrorsFrom(error.fieldErrors);
        for (const field of INVITE_FIELDS) {
          const message = fieldErrors[field];
          if (message !== undefined) {
            setError(field, { type: "server", message });
          }
        }
      },
    });
  });

  return (
    <Dialog
      open
      fullWidth
      maxWidth="sm"
      onClose={busy ? undefined : onClose}
      aria-labelledby={titleId}
    >
      <form noValidate onSubmit={(event) => void onSubmit(event)}>
        <DialogTitle id={titleId}>{INVITE_TEXTS.title}</DialogTitle>
        <DialogContent className="tw-flex tw-flex-col tw-gap-4">
          {formError ? <Alert severity="error">{formError}</Alert> : null}
          <Controller
            name="email"
            control={control}
            render={({ field: { ref, ...field }, fieldState }) => (
              <TextField
                {...field}
                inputRef={ref}
                type="email"
                autoComplete="off"
                label={INVITE_TEXTS.email}
                required
                disabled={busy}
                error={fieldState.error !== undefined}
                helperText={fieldState.error?.message ?? INVITE_TEXTS.emailHelp}
                margin="dense"
                fullWidth
              />
            )}
          />
          <Controller
            name="role"
            control={control}
            render={({ field: { ref, ...field }, fieldState }) => (
              <TextField
                {...field}
                select
                inputRef={ref}
                label={INVITE_TEXTS.role}
                required
                disabled={busy}
                error={fieldState.error !== undefined}
                helperText={fieldState.error?.message}
                fullWidth
              >
                {invitableRoles.map((role) => (
                  <MenuItem key={role} value={role}>
                    {roleLabel(role)}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={busy}>
            {INVITE_TEXTS.cancel}
          </Button>
          <Button type="submit" variant="contained" loading={busy}>
            {INVITE_TEXTS.confirm}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

export function InviteDialog(props: InviteDialogProps) {
  const [link, setLink] = useState<InvitationLink | null>(null);
  if (link !== null) {
    return <InvitationLinkDialog link={link} onClose={props.onClose} />;
  }
  return <InviteForm {...props} onLink={setLink} />;
}

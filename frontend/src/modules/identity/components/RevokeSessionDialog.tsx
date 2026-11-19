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

import { useLogout } from "../hooks/useLogout";
import { useRevokeSession } from "../hooks/useRevokeSession";
import type { Session } from "../hooks/useSessions";

// Confirmation of "Cerrar sesión" / "Cerrar esta sesión" (design.md §3.4, texts of Q-129 a).
export const CANCEL_LABEL = "Cancelar";

export const REVOKE_OTHER_TEXTS = {
  title: (device: string) => `¿Cerrar la sesión de ${device}?`,
  body: "Ese dispositivo va a tener que ingresar de nuevo con Google.",
  confirm: "Cerrar sesión",
} as const;

export const REVOKE_CURRENT_TEXTS = {
  title: "¿Cerrar esta sesión?",
  body: "Vas a volver a la pantalla de ingreso.",
  confirm: "Cerrar esta sesión",
} as const;

export type ConfirmDialogProps = Readonly<{
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  busy: boolean;
  error: ApiError | null;
}>;

// The confirmation shared by the two dialogs of "Seguridad". While the action runs nothing else
// can be pressed and the dialog does not close; a failure stays inside it with the fixed title of
// its code (`ApiError.title`, C-08), so the person can confirm again or cancel.
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  onConfirm,
  onClose,
  busy,
  error,
}: ConfirmDialogProps) {
  const titleId = useId();
  const bodyId = useId();
  return (
    <Dialog
      open
      onClose={busy ? undefined : onClose}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      <DialogContent className="tw-flex tw-flex-col tw-gap-4">
        <DialogContentText id={bodyId}>{body}</DialogContentText>
        {error ? <Alert severity="error">{error.title}</Alert> : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          {CANCEL_LABEL}
        </Button>
        <Button variant="contained" color="error" onClick={onConfirm} loading={busy}>
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

type SessionDialogProps = Readonly<{ device: string; onClose: () => void }>;

// The current session goes through the BFF logout, never its own revoke endpoint: only the BFF
// clears the cookies, and after its `204` the browser goes to "Ingresar" (design.md §3.4). Until
// the page is gone the action stays blocked.
function CurrentSessionDialog({ onClose }: SessionDialogProps) {
  const logout = useLogout();
  return (
    <ConfirmDialog
      title={REVOKE_CURRENT_TEXTS.title}
      body={REVOKE_CURRENT_TEXTS.body}
      confirmLabel={REVOKE_CURRENT_TEXTS.confirm}
      onConfirm={() => logout.mutate()}
      onClose={onClose}
      busy={logout.isPending || logout.isSuccess}
      error={logout.isError ? logout.error : null}
    />
  );
}

// Another session: closed by id; a `404` (already ended) is a success too (useRevokeSession).
function OtherSessionDialog({
  sessionId,
  device,
  onClose,
}: SessionDialogProps & { sessionId: string }) {
  const revoke = useRevokeSession();
  return (
    <ConfirmDialog
      title={REVOKE_OTHER_TEXTS.title(device)}
      body={REVOKE_OTHER_TEXTS.body}
      confirmLabel={REVOKE_OTHER_TEXTS.confirm}
      onConfirm={() => revoke.mutate(sessionId, { onSuccess: onClose })}
      onClose={onClose}
      busy={revoke.isPending}
      error={revoke.isError ? revoke.error : null}
    />
  );
}

export function RevokeSessionDialog({
  session,
  device,
  onClose,
}: Readonly<{ session: Session; device: string; onClose: () => void }>) {
  return session.is_current ? (
    <CurrentSessionDialog device={device} onClose={onClose} />
  ) : (
    <OtherSessionDialog sessionId={session.id} device={device} onClose={onClose} />
  );
}

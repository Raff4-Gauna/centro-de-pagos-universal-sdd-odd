"use client";

import ContentCopy from "@mui/icons-material/ContentCopy";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import { useId, useState } from "react";

import { formatDateTime } from "@/modules/identity/lib/format-dates";

import type { InvitationLink } from "../hooks/useInvitations";

// The invitation link, shown once (AC-TEN-24, RNF-TEN-03, Q-207, design.md §3.9): right after the
// backend's `201` of inviting or resending, for the owner or admin to copy and send. The link
// carries the token, a secret (C-06): it lives only in the state of the dialog that asked for it
// (InviteDialog, ResendInvitationDialog), which passes it here; closing unmounts both and it is
// gone. It is never in the Query cache, the URL, storage or a log, and it is not shown again: to
// get another one the invitation is resent, which voids this one. "Copiar" writes it to the
// clipboard; if the browser refuses, the field is selectable to copy it by hand. Only "Listo"
// closes it (not a click outside or Escape), so a stray click does not lose the link.
export const INVITATION_LINK_TEXTS = {
  title: "Link de invitación",
  body: (email: string, expires: string) =>
    `Mandale este link a ${email}. Vence el ${expires}. Lo puede usar solo esa persona, con su cuenta de Google de ese email.`,
  once: "Este link no se vuelve a mostrar: copialo ahora. Si se pierde, reenviá la invitación.",
  field: "Link",
  copy: "Copiar",
  copied: "Link copiado.",
  copyFailed: "No se pudo copiar: seleccioná el link y copialo a mano.",
  done: "Listo",
} as const;

type CopyState = "idle" | "copied" | "failed";

export type InvitationLinkDialogProps = Readonly<{ link: InvitationLink; onClose: () => void }>;

export function InvitationLinkDialog({ link, onClose }: InvitationLinkDialogProps) {
  const titleId = useId();
  const bodyId = useId();
  const [copy, setCopy] = useState<CopyState>("idle");

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(link.url);
      setCopy("copied");
    } catch {
      // No clipboard (an insecure context) or the browser refused: copying by hand still works.
      setCopy("failed");
    }
  }

  return (
    <Dialog open aria-labelledby={titleId} aria-describedby={bodyId} fullWidth maxWidth="sm">
      <DialogTitle id={titleId}>{INVITATION_LINK_TEXTS.title}</DialogTitle>
      <DialogContent className="tw-flex tw-flex-col tw-gap-4">
        <DialogContentText id={bodyId}>
          {INVITATION_LINK_TEXTS.body(link.email, formatDateTime(link.expiresAt))}
        </DialogContentText>
        <Alert severity="warning">{INVITATION_LINK_TEXTS.once}</Alert>
        <TextField
          label={INVITATION_LINK_TEXTS.field}
          value={link.url}
          onFocus={(event) => event.target.select()}
          slotProps={{ htmlInput: { readOnly: true, spellCheck: false } }}
          className="tw-mt-2"
          fullWidth
        />
        {copy === "copied" ? (
          <Alert severity="success" role="status">
            {INVITATION_LINK_TEXTS.copied}
          </Alert>
        ) : null}
        {copy === "failed" ? (
          <Alert severity="error">{INVITATION_LINK_TEXTS.copyFailed}</Alert>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button startIcon={<ContentCopy />} onClick={() => void copyLink()}>
          {INVITATION_LINK_TEXTS.copy}
        </Button>
        <Button variant="contained" onClick={onClose}>
          {INVITATION_LINK_TEXTS.done}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

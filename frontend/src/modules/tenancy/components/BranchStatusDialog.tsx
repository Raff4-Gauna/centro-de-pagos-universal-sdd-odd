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

import { type Branch, type BranchTransition, useChangeBranchState } from "../hooks/useBranches";

// Confirmation of "Desactivar" / "Reactivar" (RN-TEN-19, Q-211, design.md §3.9): a branch is
// never deleted. While the request runs nothing else can be pressed and the dialog does not close;
// it closes only after the backend's `200`. A refusal stays inside it:
// - reactivating onto a name or code another active branch uses is `400 validation_error` with
//   the field's message (AC-TEN-30), and the branch stays inactive;
// - `409 invalid_transition` (someone else already changed it), `organization_suspended` and the
//   rest show the fixed title of their code; the list is read again either way (useBranches).
export const BRANCH_STATUS_TEXTS = {
  deactivate: {
    title: (name: string) => `¿Desactivar ${name}?`,
    body: "Deja de admitir cobros nuevos; los cobros pendientes, sus vínculos y el histórico no cambian. Se puede reactivar después.",
    confirm: "Desactivar",
  },
  reactivate: {
    title: (name: string) => `¿Reactivar ${name}?`,
    body: "Vuelve a quedar activa, con su nombre y su código.",
    confirm: "Reactivar",
  },
  cancel: "Cancelar",
} as const;

function errorText(error: ApiError): string {
  if (error.code === "validation_error") {
    const [first] = error.fieldErrors;
    if (first !== undefined) {
      return first.message;
    }
  }
  return error.title;
}

export type BranchStatusDialogProps = Readonly<{
  organizationId: string;
  branch: Branch;
  transition: BranchTransition;
  onClose: () => void;
}>;

export function BranchStatusDialog({
  organizationId,
  branch,
  transition,
  onClose,
}: BranchStatusDialogProps) {
  const titleId = useId();
  const bodyId = useId();
  const change = useChangeBranchState(organizationId);
  const texts = BRANCH_STATUS_TEXTS[transition];
  const busy = change.isPending;
  return (
    <Dialog
      open
      onClose={busy ? undefined : onClose}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
    >
      <DialogTitle id={titleId}>{texts.title(branch.name)}</DialogTitle>
      <DialogContent className="tw-flex tw-flex-col tw-gap-4">
        <DialogContentText id={bodyId}>{texts.body}</DialogContentText>
        {change.isError ? <Alert severity="error">{errorText(change.error)}</Alert> : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          {BRANCH_STATUS_TEXTS.cancel}
        </Button>
        <Button
          variant="contained"
          color={transition === "deactivate" ? "error" : "primary"}
          loading={busy}
          onClick={() => change.mutate({ branchId: branch.id, transition }, { onSuccess: onClose })}
        >
          {texts.confirm}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

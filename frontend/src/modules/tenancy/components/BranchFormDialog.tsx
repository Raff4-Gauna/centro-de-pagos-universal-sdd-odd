"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import { type FormEvent, useId, useState } from "react";

import type { ApiError } from "@/lib/problem";

import { type Branch, useCreateBranch, useUpdateBranch } from "../hooks/useBranches";
import {
  BRANCH_FIELDS,
  type BranchField,
  type BranchFieldErrors,
  type BranchValues,
  branchFieldErrorsFrom,
  changedBranchValues,
  EMPTY_BRANCH_VALUES,
  trimBranchValues,
  validateBranchValues,
} from "../lib/branch-form";

// "Nueva sucursal" and "Editar sucursal" (RF-TEN-06, design.md §3.9, §6). The form is checked
// before sending (lib/branch-form.ts) and again by the backend:
// - `400 validation_error`: each message goes under its field;
// - `409 conflict`: another active branch uses the name or the code (AC-TEN-38); the backend's
//   `detail` says which, in plain text, above the fields;
// - anything else (`organization_suspended`, `403`, `404`): the fixed title of its code.
// While the request runs nothing else can be pressed and the dialog does not close; it closes only
// after the backend's `2xx`. An edit sends only what changed; with no change it just closes.
export const BRANCH_FORM_TEXTS = {
  createTitle: "Nueva sucursal",
  editTitle: "Editar sucursal",
  create: "Crear",
  save: "Guardar",
  cancel: "Cancelar",
  labels: { name: "Nombre", code: "Código (opcional)", address: "Dirección (opcional)" },
} as const;

function valuesOf(branch: Branch | null): BranchValues {
  return branch === null
    ? EMPTY_BRANCH_VALUES
    : { name: branch.name, code: branch.code, address: branch.address };
}

// The message above the fields: the field errors already sit under their field.
function formErrorText(error: ApiError, fieldErrors: BranchFieldErrors): string | null {
  if (error.code === "conflict") {
    return error.detail ?? error.title;
  }
  if (error.code === "validation_error" && Object.keys(fieldErrors).length > 0) {
    return null;
  }
  return error.title;
}

export type BranchFormDialogProps = Readonly<{
  organizationId: string;
  // null: a new branch.
  branch: Branch | null;
  onClose: () => void;
}>;

export function BranchFormDialog({ organizationId, branch, onClose }: BranchFormDialogProps) {
  const titleId = useId();
  const create = useCreateBranch(organizationId);
  const update = useUpdateBranch(organizationId);
  const initial = valuesOf(branch);
  const [values, setValues] = useState<BranchValues>(initial);
  const [clientErrors, setClientErrors] = useState<BranchFieldErrors>({});
  const mutation = branch === null ? create : update;
  const busy = mutation.isPending;
  const serverError = mutation.isError ? mutation.error : null;
  const serverFieldErrors = serverError ? branchFieldErrorsFrom(serverError.fieldErrors) : {};
  const fieldErrors = { ...serverFieldErrors, ...clientErrors };
  const formError = serverError ? formErrorText(serverError, serverFieldErrors) : null;

  function onChange(field: BranchField, value: string) {
    setValues((previous) => ({ ...previous, [field]: value }));
    setClientErrors((previous) => ({ ...previous, [field]: undefined }));
    if (mutation.isError) {
      mutation.reset(); // The backend's answer was about the values before this change.
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validateBranchValues(values);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }
    if (branch === null) {
      const { name, code, address } = trimBranchValues(values);
      create.mutate({ name, code, address }, { onSuccess: onClose });
      return;
    }
    const changes = changedBranchValues(initial, values);
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    update.mutate({ branchId: branch.id, changes }, { onSuccess: onClose });
  }

  return (
    <Dialog
      open
      fullWidth
      maxWidth="sm"
      onClose={busy ? undefined : onClose}
      aria-labelledby={titleId}
    >
      <form noValidate onSubmit={onSubmit}>
        <DialogTitle id={titleId}>
          {branch === null ? BRANCH_FORM_TEXTS.createTitle : BRANCH_FORM_TEXTS.editTitle}
        </DialogTitle>
        <DialogContent className="tw-flex tw-flex-col tw-gap-4">
          {formError ? <Alert severity="error">{formError}</Alert> : null}
          {BRANCH_FIELDS.map((field) => (
            <TextField
              key={field}
              name={field}
              label={BRANCH_FORM_TEXTS.labels[field]}
              value={values[field]}
              required={field === "name"}
              disabled={busy}
              error={fieldErrors[field] !== undefined}
              helperText={fieldErrors[field]}
              onChange={(event) => onChange(field, event.target.value)}
              margin="dense"
              fullWidth
            />
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={busy}>
            {BRANCH_FORM_TEXTS.cancel}
          </Button>
          <Button type="submit" variant="contained" loading={busy}>
            {branch === null ? BRANCH_FORM_TEXTS.create : BRANCH_FORM_TEXTS.save}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

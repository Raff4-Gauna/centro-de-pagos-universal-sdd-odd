"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";

import type { ApiError } from "@/lib/problem";

import type { CurrentOrganizationDetails } from "../hooks/useCurrentOrganizationDetails";
import { useUpdateOrganization } from "../hooks/useUpdateOrganization";
import {
  changedCompanyValues,
  COMPANY_FIELDS,
  type CompanyFieldErrors,
  companyFieldErrorsFrom,
  companyResolver,
  type CompanyValues,
  companyValuesOf,
} from "../lib/company-form";

// The form of "Datos de la empresa" (RF-TEN-03, Q-209, design.md §3.9), with react-hook-form and
// the zod schema of lib/company-form.ts (07 §3.3, Q-239). Shown only when the company's
// `allowed_actions` bring `org.update` (CompanyScreen); the backend checks every request again:
// - `400 validation_error`: each message goes under its field;
// - anything else (`organization_suspended`, `403`, `503 organization_busy`, …): the fixed title
//   of its code above the fields; `organization_busy`'s is the text the owner decided (Q-230).
// The time zone is shown but not edited yet: which zones to offer is open (Q-240).
// A save sends only what changed, and with no change sends nothing. The values become the saved
// ones only after the backend's `2xx`, with its answer. The form is built for one company
// (`key={organizationId}`): switching company discards what was typed.
export const COMPANY_FORM_TEXTS = {
  labels: {
    name: "Nombre",
    legal_name: "Razón social (opcional)",
    tax_id: "CUIT (opcional)",
    timezone: "Zona horaria",
  },
  taxIdHelp: "11 dígitos, con o sin guiones.",
  timezoneHelp: "Por ahora no se puede cambiar desde acá.",
  save: "Guardar",
  discard: "Descartar cambios",
  saved: "Datos guardados.",
} as const;

// The message above the fields: the field errors already sit under their field.
function formErrorText(error: ApiError, fieldErrors: CompanyFieldErrors): string | null {
  if (error.code === "validation_error" && Object.keys(fieldErrors).length > 0) {
    return null;
  }
  return error.title;
}

export type CompanyDataFormProps = Readonly<{
  organizationId: string;
  details: CurrentOrganizationDetails;
}>;

export function CompanyDataForm({ organizationId, details }: CompanyDataFormProps) {
  const update = useUpdateOrganization(organizationId);
  // What the backend last said the company is: the base of "what changed" and of "Descartar".
  const [saved, setSaved] = useState<CompanyValues>(() => companyValuesOf(details));
  const { control, handleSubmit, reset, setError, formState } = useForm<CompanyValues>({
    defaultValues: saved,
    resolver: companyResolver,
  });
  const busy = update.isPending;
  const serverError = update.isError ? update.error : null;
  const formError = serverError
    ? formErrorText(serverError, companyFieldErrorsFrom(serverError.fieldErrors))
    : null;

  const onSubmit = handleSubmit((values) => {
    const changes = changedCompanyValues(saved, values);
    if (Object.keys(changes).length === 0) {
      reset(saved);
      return;
    }
    update.mutate(changes, {
      onSuccess: (data) => {
        const next = companyValuesOf(data);
        setSaved(next);
        reset(next);
      },
      onError: (error) => {
        const fieldErrors = companyFieldErrorsFrom(error.fieldErrors);
        for (const field of COMPANY_FIELDS) {
          const message = fieldErrors[field];
          if (message !== undefined) {
            setError(field, { type: "server", message });
          }
        }
      },
    });
  });

  return (
    <form
      noValidate
      onSubmit={(event) => void onSubmit(event)}
      className="tw-flex tw-flex-col tw-gap-4"
    >
      {formError ? <Alert severity="error">{formError}</Alert> : null}
      {update.isSuccess && !formState.isDirty ? (
        <Alert severity="success">{COMPANY_FORM_TEXTS.saved}</Alert>
      ) : null}
      {(["name", "legal_name", "tax_id"] as const).map((name) => (
        <Controller
          key={name}
          name={name}
          control={control}
          render={({ field: { ref, ...field }, fieldState }) => (
            <TextField
              {...field}
              inputRef={ref}
              label={COMPANY_FORM_TEXTS.labels[name]}
              required={name === "name"}
              disabled={busy}
              error={fieldState.error !== undefined}
              helperText={
                fieldState.error?.message ??
                (name === "tax_id" ? COMPANY_FORM_TEXTS.taxIdHelp : undefined)
              }
              fullWidth
            />
          )}
        />
      ))}
      {/* Which zones the form offers is open (Q-240): until then the zone is shown, not edited. */}
      <TextField
        name="timezone"
        label={COMPANY_FORM_TEXTS.labels.timezone}
        value={details.timezone}
        helperText={COMPANY_FORM_TEXTS.timezoneHelp}
        slotProps={{ input: { readOnly: true } }}
        fullWidth
      />
      <div className="tw-flex tw-justify-end tw-gap-2">
        <Button onClick={() => reset(saved)} disabled={busy || !formState.isDirty}>
          {COMPANY_FORM_TEXTS.discard}
        </Button>
        <Button type="submit" variant="contained" loading={busy} disabled={!formState.isDirty}>
          {COMPANY_FORM_TEXTS.save}
        </Button>
      </div>
    </form>
  );
}

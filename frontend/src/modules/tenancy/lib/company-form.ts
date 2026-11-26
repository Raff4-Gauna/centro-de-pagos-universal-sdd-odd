import type { Resolver } from "react-hook-form";
import { z } from "zod";

import { flatZodResolver } from "@/lib/form-resolver";
import type { ProblemFieldError } from "@/lib/problem";

import type { CurrentOrganizationDetails } from "../hooks/useCurrentOrganizationDetails";
import { timezoneOptions } from "./timezones";

// The values of "Datos de la empresa" and their check before sending (RF-TEN-03, Q-209, design.md
// §3.9, §5, §6), as a zod schema (07 §3.3, Q-239). It repeats what the contract and the backend
// say so the person sees the mistake at once; the backend validates again and has the last word:
// spaces removed at both ends, `name` required and up to 120 characters, `legal_name` up to 200,
// `tax_id` (CUIT) empty or 11 digits, plain or `XX-XXXXXXXX-X` (the check digit is the backend's),
// and `timezone` one of the list of lib/timezones.ts (Q-240) or the company's current zone, so a
// zone set by an operator does not block saving the other fields. Empty `legal_name` or `tax_id`
// clears it. The messages are the backend's own for the same mistake.
export const COMPANY_FIELDS = ["name", "legal_name", "tax_id", "timezone"] as const;
export type CompanyField = (typeof COMPANY_FIELDS)[number];
export type CompanyValues = Record<CompanyField, string>;
export type CompanyFieldErrors = Partial<Record<CompanyField, string>>;

export const COMPANY_MAX_LENGTH = { name: 120, legal_name: 200 } as const;

export const COMPANY_FORM_ERRORS = {
  nameRequired: "El nombre es obligatorio.",
  tooLong: (limit: number) => `Como máximo ${limit} caracteres.`,
  taxIdInvalid: "No es un CUIT válido.",
  timezoneInvalid: "Elegí una zona horaria de la lista.",
} as const;

// ASCII digits only, as the backend (`domain/tax_id.py`): `\d` without the `u` flag.
const TAX_ID_FORMAT = /^(?:\d{11}|\d{2}-\d{8}-\d)?$/;

// One schema per form: the time zones it accepts depend on the company's current one.
export function companySchema(currentTimezone: string) {
  const zones = timezoneOptions(currentTimezone) as readonly [string, ...string[]];
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, COMPANY_FORM_ERRORS.nameRequired)
      .max(COMPANY_MAX_LENGTH.name, COMPANY_FORM_ERRORS.tooLong(COMPANY_MAX_LENGTH.name)),
    legal_name: z
      .string()
      .trim()
      .max(
        COMPANY_MAX_LENGTH.legal_name,
        COMPANY_FORM_ERRORS.tooLong(COMPANY_MAX_LENGTH.legal_name),
      ),
    tax_id: z.string().trim().regex(TAX_ID_FORMAT, COMPANY_FORM_ERRORS.taxIdInvalid),
    timezone: z.enum(zones, { error: COMPANY_FORM_ERRORS.timezoneInvalid }),
  }) satisfies z.ZodType<CompanyValues, CompanyValues>;
}

// The schema as react-hook-form's resolver: the trimmed values when they pass, the first message
// of each field when they do not.
export function companyResolver(currentTimezone: string): Resolver<CompanyValues> {
  return flatZodResolver(companySchema(currentTimezone));
}

export function companyValuesOf(details: CurrentOrganizationDetails): CompanyValues {
  return {
    name: details.name,
    legal_name: details.legal_name,
    tax_id: details.tax_id,
    timezone: details.timezone,
  };
}

// The backend keeps the CUIT as 11 digits: the same number with hyphens is no change.
function comparable(field: CompanyField, value: string): string {
  const trimmed = value.trim();
  return field === "tax_id" ? trimmed.replaceAll("-", "") : trimmed;
}

// The fields that differ from the company as it was loaded: only those travel in the `PATCH`, so
// a save never rewrites what the person did not touch.
export function changedCompanyValues(
  initial: CompanyValues,
  values: CompanyValues,
): Partial<CompanyValues> {
  const changes: Partial<CompanyValues> = {};
  for (const field of COMPANY_FIELDS) {
    if (comparable(field, initial[field]) !== comparable(field, values[field])) {
      changes[field] = values[field].trim();
    }
  }
  return changes;
}

// The backend's `400 validation_error` on the form's fields; a field the form does not have
// (`unknown_field` on another key) stays out and the screen shows the error's title instead.
export function companyFieldErrorsFrom(errors: readonly ProblemFieldError[]): CompanyFieldErrors {
  const result: CompanyFieldErrors = {};
  for (const { field, message } of errors) {
    if (
      (COMPANY_FIELDS as readonly string[]).includes(field) &&
      result[field as CompanyField] === undefined
    ) {
      result[field as CompanyField] = message;
    }
  }
  return result;
}

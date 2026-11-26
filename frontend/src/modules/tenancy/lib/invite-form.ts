import type { Resolver } from "react-hook-form";
import { z } from "zod";

import { flatZodResolver } from "@/lib/form-resolver";
import type { ProblemFieldError } from "@/lib/problem";

import type { Role } from "./role-labels";

// The values of "Invitar" and their check before sending (RF-TEN-05, design.md §3.9, §6), as a
// zod schema (07 §3.3, Q-239). It repeats what the contract and the backend say so the person sees
// the mistake at once; the backend validates again and has the last word:
// - `email`: spaces removed at both ends, required, at most 254 characters and shaped as an
//   address (something, one `@`, something, no spaces). The full check (Django's EmailValidator)
//   is the backend's: a stricter one here could refuse an address the backend takes.
// - `role`: one of the company's `invitable_roles` (GET /api/organizations/current/), which the
//   backend computed for the person asking; nothing is picked at first, so it is always a choice.
// The message of an invalid email is the backend's own for the same mistake.
export const INVITE_FIELDS = ["email", "role"] as const;
export type InviteField = (typeof INVITE_FIELDS)[number];
// The role is text while editing ("" = none picked); the schema narrows it to a `Role`.
export type InviteValues = { email: string; role: string };
export type InviteRequest = { email: string; role: Role };
export type InviteFieldErrors = Partial<Record<InviteField, string>>;

export const INVITE_EMAIL_MAX_LENGTH = 254;

export const INVITE_FORM_ERRORS = {
  emailRequired: "El email es obligatorio.",
  emailInvalid: "Tiene que ser un email válido.",
  roleRequired: "Elegí un rol.",
} as const;

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+$/;

export const EMPTY_INVITE: InviteValues = { email: "", role: "" };

export function inviteSchema(invitableRoles: readonly Role[]) {
  return z.object({
    email: z
      .string()
      .trim()
      .min(1, INVITE_FORM_ERRORS.emailRequired)
      .max(INVITE_EMAIL_MAX_LENGTH, INVITE_FORM_ERRORS.emailInvalid)
      .regex(EMAIL_SHAPE, INVITE_FORM_ERRORS.emailInvalid),
    role: z
      .string()
      .refine((value): value is Role => (invitableRoles as readonly string[]).includes(value), {
        error: INVITE_FORM_ERRORS.roleRequired,
      }),
  }) satisfies z.ZodType<InviteRequest, InviteValues>;
}

export function inviteResolver(
  invitableRoles: readonly Role[],
): Resolver<InviteValues, unknown, InviteRequest> {
  return flatZodResolver(inviteSchema(invitableRoles));
}

// The backend's `400 validation_error` on the form's fields; a field the form does not have
// (`unknown_field` on another key) stays out and the dialog shows the error's text instead.
export function inviteFieldErrorsFrom(errors: readonly ProblemFieldError[]): InviteFieldErrors {
  const result: InviteFieldErrors = {};
  for (const { field, message } of errors) {
    if (
      (INVITE_FIELDS as readonly string[]).includes(field) &&
      result[field as InviteField] === undefined
    ) {
      result[field as InviteField] = message;
    }
  }
  return result;
}

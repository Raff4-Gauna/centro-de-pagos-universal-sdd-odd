import type { ProblemFieldError } from "@/lib/problem";

// The values of the branch form and their check before sending (design.md §5, §6). It repeats
// the contract's limits so the person sees the mistake at once; the backend validates again and
// has the last word (07 §3.3): spaces removed at both ends, `name` required and up to 120
// characters, `code` up to 32 and `address` up to 255 (empty is "not informed").
export const BRANCH_FIELDS = ["name", "code", "address"] as const;
export type BranchField = (typeof BRANCH_FIELDS)[number];
export type BranchValues = Record<BranchField, string>;
export type BranchFieldErrors = Partial<Record<BranchField, string>>;

export const BRANCH_MAX_LENGTH: Readonly<Record<BranchField, number>> = {
  name: 120,
  code: 32,
  address: 255,
};

export const BRANCH_FORM_ERRORS = {
  nameRequired: "El nombre es obligatorio.",
  tooLong: (limit: number) => `Como máximo ${limit} caracteres.`,
} as const;

export const EMPTY_BRANCH_VALUES: BranchValues = { name: "", code: "", address: "" };

export function trimBranchValues(values: BranchValues): BranchValues {
  return { name: values.name.trim(), code: values.code.trim(), address: values.address.trim() };
}

export function validateBranchValues(values: BranchValues): BranchFieldErrors {
  const trimmed = trimBranchValues(values);
  const errors: BranchFieldErrors = {};
  for (const field of BRANCH_FIELDS) {
    if (trimmed[field].length > BRANCH_MAX_LENGTH[field]) {
      errors[field] = BRANCH_FORM_ERRORS.tooLong(BRANCH_MAX_LENGTH[field]);
    }
  }
  if (trimmed.name === "") {
    errors.name = BRANCH_FORM_ERRORS.nameRequired;
  }
  return errors;
}

// The fields of an edit that differ from the branch as it was loaded: only those travel in the
// `PATCH`, so an edit never rewrites what the person did not touch.
export function changedBranchValues(
  initial: BranchValues,
  values: BranchValues,
): Partial<BranchValues> {
  const before = trimBranchValues(initial);
  const after = trimBranchValues(values);
  const changes: Partial<BranchValues> = {};
  for (const field of BRANCH_FIELDS) {
    if (before[field] !== after[field]) {
      changes[field] = after[field];
    }
  }
  return changes;
}

// The backend's `400 validation_error` on the form's fields; a field the form does not have
// (`unknown_field` on another key) stays out and the screen shows the error's title instead.
export function branchFieldErrorsFrom(errors: readonly ProblemFieldError[]): BranchFieldErrors {
  const result: BranchFieldErrors = {};
  for (const { field, message } of errors) {
    if (
      (BRANCH_FIELDS as readonly string[]).includes(field) &&
      result[field as BranchField] === undefined
    ) {
      result[field as BranchField] = message;
    }
  }
  return result;
}

import type { ApiError } from "@/lib/problem";

// What a dialog of "Invitaciones pendientes" says when the backend refuses (design.md §4.3, §6).
// Three codes get the screen's own text: `invitation_pending` has no fixed title (the envelope
// falls back to the English HTTP phrase), and `already_member` and `invalid_transition` are worded
// for the API, not for the person. Every other refusal shows the fixed `title` of its code:
// `organization_busy` has the text the owner decided for the UI (Q-230), and `forbidden`,
// `organization_suspended`, `not_found` and the rest are fixed per code (problems.py). Never the
// `detail`: it is the backend's, and the UI words its own messages (C-08).
export const INVITATION_ERROR_TEXTS = {
  already_member: "Esa persona ya es miembro de la empresa.",
  invitation_pending:
    "Ya hay una invitación pendiente para ese email: reenviala desde Invitaciones pendientes.",
  invalid_transition: "Esta invitación ya no está pendiente.",
} as const;

export function invitationErrorText(error: ApiError): string {
  return Object.hasOwn(INVITATION_ERROR_TEXTS, error.code)
    ? INVITATION_ERROR_TEXTS[error.code as keyof typeof INVITATION_ERROR_TEXTS]
    : error.title;
}

import type { ApiError } from "@/lib/problem";

// What a dialog of "Colaboradores" says when the backend refuses (design.md §4.2, §6). The backend's
// `detail` of `last_owner` names the role by its code, so the screen explains it with its own text
// (Q-232: the UI never shows a role code). Every other refusal shows the fixed `title` of its code:
// `organization_busy` has the text the owner decided for the UI (Q-230), and `invalid_transition`,
// `organization_suspended`, `forbidden` and the rest are fixed per code (problems.py).
export const LAST_OWNER_TEXT =
  "La empresa tiene que conservar al menos un Dueño. Asigná el rol Dueño a otra persona antes.";

export function memberErrorText(error: ApiError): string {
  return error.code === "last_owner" ? LAST_OWNER_TEXT : error.title;
}

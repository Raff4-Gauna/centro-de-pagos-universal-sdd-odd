import type { components } from "@/types/api";

// How the UI names a role (Q-232, decided by the owner on 2026-11-20). The API keeps the codes;
// every screen that shows a role reads its label here, never the code. Typed over the generated
// enum: a new role in the contract does not compile until it gets its label.
export type Role = components["schemas"]["RoleEnum"];

export const ROLE_LABELS: Readonly<Record<Role, string>> = {
  owner: "Dueño",
  admin: "Administrador",
  operator: "Operador",
  viewer: "Solo lectura",
};

export function roleLabel(role: Role): string {
  return ROLE_LABELS[role];
}

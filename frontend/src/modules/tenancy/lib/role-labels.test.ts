import { describe, expect, it } from "vitest";

import { ROLE_LABELS, roleLabel } from "./role-labels";

// Q-232: one label per role of the contract, in Spanish.
describe("role labels (Q-232)", () => {
  it("names every role of the contract in Spanish", () => {
    expect(ROLE_LABELS).toEqual({
      owner: "Dueño",
      admin: "Administrador",
      operator: "Operador",
      viewer: "Solo lectura",
    });
    expect(roleLabel("viewer")).toBe("Solo lectura");
  });
});

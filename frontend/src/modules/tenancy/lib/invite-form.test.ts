import { describe, expect, it } from "vitest";

import {
  INVITE_EMAIL_MAX_LENGTH,
  INVITE_FORM_ERRORS,
  inviteFieldErrorsFrom,
  inviteResolver,
} from "./invite-form";

// The check of "Invitar" before sending (RF-TEN-05, Q-239): what the backend would refuse anyway,
// said at once; the backend validates again and has the last word.
async function resolve(email: string, role: string, roles = ["operator", "viewer"] as const) {
  const resolver = inviteResolver([...roles]);
  return resolver({ email, role }, undefined, { fields: {}, shouldUseNativeValidation: false });
}

describe("invite form (RF-TEN-05, Q-239)", () => {
  it("test_RF_TEN_05_trims_the_email_and_accepts_an_invitable_role", async () => {
    const result = await resolve("  ana@acme.test ", "operator");
    expect(result.errors).toEqual({});
    expect(result.values).toEqual({ email: "ana@acme.test", role: "operator" });
  });

  it.each([
    ["", INVITE_FORM_ERRORS.emailRequired],
    ["   ", INVITE_FORM_ERRORS.emailRequired],
    ["sin-arroba", INVITE_FORM_ERRORS.emailInvalid],
    ["dos@@acme.test", INVITE_FORM_ERRORS.emailInvalid],
    ["con espacio@acme.test", INVITE_FORM_ERRORS.emailInvalid],
    [`${"a".repeat(INVITE_EMAIL_MAX_LENGTH)}@x`, INVITE_FORM_ERRORS.emailInvalid],
  ])("test_RF_TEN_05_email_%j_is_refused", async (email, message) => {
    const result = await resolve(email, "operator");
    expect(result.errors.email?.message).toBe(message);
  });

  it.each(["", "owner", "admin"])(
    "test_RF_TEN_05_role_%j_not_invitable_is_refused",
    async (role) => {
      const result = await resolve("ana@acme.test", role);
      expect(result.errors.role?.message).toBe(INVITE_FORM_ERRORS.roleRequired);
    },
  );

  it("test_RF_TEN_05_server_field_errors_keep_only_the_form_fields", () => {
    expect(
      inviteFieldErrorsFrom([
        { field: "email", code: "invalid", message: "Tiene que ser un email válido." },
        { field: "email", code: "other", message: "segundo" },
        { field: "purpose", code: "unknown_field", message: "Campo desconocido." },
      ]),
    ).toEqual({ email: "Tiene que ser un email válido." });
  });
});

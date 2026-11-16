import { describe, expect, it, vi } from "vitest";

import { LOGIN_ERROR_CODES } from "@/lib/server/login-flow";

import { GENERIC_LOGIN_ERROR, LOGIN_ERROR_TEXTS, loginErrorCodeOf } from "./login-errors";

// `login-flow.ts` is server-only; its allowlist is read here only to compare the two lists.
vi.mock("server-only", () => ({}));

describe("login-errors (AC-IDA-19, spec §14, design.md §3.4)", () => {
  it("test_AC_IDA_19_unknown_code_shows_the_generic_text", () => {
    for (const raw of [
      "access_denied",
      "INTERNAL_ERROR",
      "",
      "<script>",
      "__proto__",
      "toString",
    ]) {
      expect(loginErrorCodeOf(raw)).toBe("internal_error");
    }
    expect(GENERIC_LOGIN_ERROR).toBe("No pudimos completar el ingreso. Probá de nuevo");
    expect(LOGIN_ERROR_TEXTS.internal_error.message).toBe(GENERIC_LOGIN_ERROR);
  });

  it("test_AC_IDA_19_repeated_error_parameter_is_not_picked_from", () => {
    expect(loginErrorCodeOf(["not_invited", "rate_limited"])).toBe("internal_error");
  });

  it("test_AC_IDA_19_no_error_parameter_shows_no_error", () => {
    expect(loginErrorCodeOf(undefined)).toBeNull();
  });

  it("test_AC_IDA_19_every_allowlisted_code_has_a_text_and_nothing_else_does", () => {
    expect(Object.keys(LOGIN_ERROR_TEXTS).sort()).toEqual([...LOGIN_ERROR_CODES].sort());
    for (const code of LOGIN_ERROR_CODES) {
      expect(loginErrorCodeOf(code)).toBe(code);
    }
  });

  it.each([
    ["login_cancelled", "Cancelaste el ingreso con Google"],
    ["email_not_verified", "Tu email de Google no está verificado"],
    ["not_invited", "Pedile a un administrador de tu empresa que te invite"],
    ["user_inactive", "Tu acceso está desactivado. Contactá al soporte"],
    ["identity_conflict", "No pudimos verificar tu cuenta; contactá al soporte"],
    ["rate_limited", "Esperá unos minutos y volvé a intentar"],
    ["google_unavailable", "Google no responde en este momento. Probá de nuevo en unos minutos"],
    ["login_disabled", "El ingreso está deshabilitado por el momento. Contactá al soporte"],
    ["session_expired", "Tu sesión venció, ingresá de nuevo"],
    ["google_auth_failed", GENERIC_LOGIN_ERROR],
    ["internal_error", GENERIC_LOGIN_ERROR],
  ] as const)("test_AC_IDA_19_%s_shows_the_text_of_section_14", (code, message) => {
    expect(LOGIN_ERROR_TEXTS[code].message).toBe(message);
  });

  it("test_AC_IDA_19_only_google_unavailable_offers_a_retry", () => {
    const withRetry = LOGIN_ERROR_CODES.filter((code) => LOGIN_ERROR_TEXTS[code].retry);
    expect(withRetry).toEqual(["google_unavailable"]);
  });
});

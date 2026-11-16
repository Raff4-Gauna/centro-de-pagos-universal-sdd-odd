import type { LoginErrorCode } from "@/lib/server/login-flow";

// What "Ingresar" says for each `/login?error=` code (spec §14, design.md §3.4, Q-127). The keys
// are the BFF's allowlist (lib/server/login-flow.ts, design.md §6.3): `Record` makes the compiler
// demand a text for every code and refuse any other key, so the two lists cannot drift. Only the
// type crosses over; the server module never reaches the browser. The value of the URL is never
// shown: an unknown code, a repeated parameter or an empty one get the generic text.
export type { LoginErrorCode };

export type LoginErrorText = Readonly<{
  message: string;
  severity: "error" | "info";
  // "Reintentar" goes back to the same start, with the same return_to (Q-127).
  retry: boolean;
}>;

export const GENERIC_LOGIN_ERROR = "No pudimos completar el ingreso. Probá de nuevo";

const generic: LoginErrorText = { message: GENERIC_LOGIN_ERROR, severity: "error", retry: false };

function error(message: string): LoginErrorText {
  return { message, severity: "error", retry: false };
}

export const LOGIN_ERROR_TEXTS: Readonly<Record<LoginErrorCode, LoginErrorText>> = {
  login_cancelled: { message: "Cancelaste el ingreso con Google", severity: "info", retry: false },
  google_auth_failed: generic,
  google_unavailable: {
    message: "Google no responde en este momento. Probá de nuevo en unos minutos",
    severity: "error",
    retry: true,
  },
  email_not_verified: error("Tu email de Google no está verificado"),
  not_invited: error("Pedile a un administrador de tu empresa que te invite"),
  user_inactive: error("Tu acceso está desactivado. Contactá al soporte"),
  identity_conflict: error("No pudimos verificar tu cuenta; contactá al soporte"),
  rate_limited: error("Esperá unos minutos y volvé a intentar"),
  login_disabled: error("El ingreso está deshabilitado por el momento. Contactá al soporte"),
  session_expired: {
    message: "Tu sesión venció, ingresá de nuevo",
    severity: "info",
    retry: false,
  },
  internal_error: generic,
};

// The code to show for the `error` query parameter: null without one, the code itself if it is in
// the allowlist, `internal_error` for anything else (`Object.hasOwn`, so `toString` or `__proto__`
// are not codes).
export function loginErrorCodeOf(raw: string | string[] | undefined): LoginErrorCode | null {
  if (raw === undefined) {
    return null;
  }
  if (typeof raw === "string" && Object.hasOwn(LOGIN_ERROR_TEXTS, raw)) {
    return raw as LoginErrorCode;
  }
  return "internal_error";
}

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LOGIN_ERROR_TEXTS } from "../lib/login-errors";
import { LoginErrorAlert } from "./LoginErrorAlert";

const START = "/api/auth/google/start?return_to=%2Fcobros";

describe("LoginErrorAlert (AC-IDA-19, spec §14)", () => {
  it("test_AC_IDA_19_google_unavailable_offers_retry_back_to_start", () => {
    render(<LoginErrorAlert code="google_unavailable" retryHref={START} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Google no responde en este momento. Probá de nuevo en unos minutos",
    );
    // A full navigation to the same start, with the same return_to: never a fetch.
    expect(screen.getByRole("link", { name: "Reintentar" })).toHaveAttribute("href", START);
  });

  it("test_AC_IDA_19_login_disabled_has_no_button", () => {
    render(<LoginErrorAlert code="login_disabled" retryHref={START} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "El ingreso está deshabilitado por el momento. Contactá al soporte",
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it.each([
    "not_invited",
    "user_inactive",
    "identity_conflict",
    "rate_limited",
    "internal_error",
  ] as const)("test_AC_IDA_19_%s_shows_its_text_without_retry", (code) => {
    render(<LoginErrorAlert code={code} retryHref={START} />);
    expect(screen.getByRole("alert")).toHaveTextContent(LOGIN_ERROR_TEXTS[code].message);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

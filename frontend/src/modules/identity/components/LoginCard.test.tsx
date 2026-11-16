import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { GENERIC_LOGIN_ERROR } from "../lib/login-errors";
import { LoginCard, REDIRECTING_LABEL, START_LABEL } from "./LoginCard";

const START = "/api/auth/google/start?return_to=%2Fcobros";

// jsdom does not navigate: the click is stopped at the document, after React saw it.
function stopNavigation(event: Event) {
  event.preventDefault();
}

beforeEach(() => {
  document.addEventListener("click", stopNavigation);
});

afterEach(() => {
  document.removeEventListener("click", stopNavigation);
});

describe("LoginCard (AC-IDA-19, spec §14, design.md §3.4)", () => {
  it("test_AC_IDA_19_single_button_is_a_full_navigation_to_start", () => {
    render(<LoginCard startHref={START} error={null} />);
    expect(screen.getByRole("heading", { name: "Ingresar" })).toBeInTheDocument();
    const button = screen.getByRole("link", { name: START_LABEL });
    expect(START_LABEL).toBe("Ingresar con Google");
    expect(button).toHaveAttribute("href", START);
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("test_AC_IDA_19_click_shows_redirecting_and_blocks_a_second_click", async () => {
    render(<LoginCard startHref={START} error={null} />);
    await userEvent.click(screen.getByRole("link", { name: START_LABEL }));
    expect(REDIRECTING_LABEL).toBe("Redirigiendo a Google…");
    const loading = screen.getByRole("link", { name: new RegExp(REDIRECTING_LABEL) });
    expect(loading).toHaveAttribute("aria-disabled", "true");
  });

  it("test_AC_IDA_19_back_from_google_restores_the_button", async () => {
    render(<LoginCard startHref={START} error={null} />);
    await userEvent.click(screen.getByRole("link", { name: START_LABEL }));
    // Coming back with the browser's Back button restores the page from the bfcache.
    act(() => {
      fireEvent(window, Object.assign(new Event("pageshow"), { persisted: true }));
    });
    expect(screen.getByRole("link", { name: START_LABEL })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("test_AC_IDA_19_error_is_shown_above_the_button", () => {
    render(<LoginCard startHref={START} error="internal_error" />);
    expect(screen.getByRole("alert")).toHaveTextContent(GENERIC_LOGIN_ERROR);
    expect(screen.getByRole("link", { name: START_LABEL })).toBeInTheDocument();
  });

  it("test_AC_IDA_19_session_expired_is_shown", () => {
    render(<LoginCard startHref={START} error="session_expired" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Tu sesión venció, ingresá de nuevo");
  });

  it("test_AC_IDA_19_login_cancelled_is_shown", () => {
    render(<LoginCard startHref={START} error="login_cancelled" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Cancelaste el ingreso con Google");
  });

  it("test_AC_IDA_19_email_not_verified_is_shown", () => {
    render(<LoginCard startHref={START} error="email_not_verified" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Tu email de Google no está verificado");
  });

  it("test_AC_IDA_19_google_unavailable_retry_uses_the_same_start", () => {
    render(<LoginCard startHref={START} error="google_unavailable" />);
    expect(screen.getByRole("link", { name: "Reintentar" })).toHaveAttribute("href", START);
  });
});

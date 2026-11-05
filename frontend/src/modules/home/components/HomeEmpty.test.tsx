import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import HomeError from "@/app/(dashboard)/inicio/error";
import HomeLoading from "@/app/(dashboard)/inicio/loading";
import HomePage from "@/app/(dashboard)/inicio/page";

import { HOME_EMPTY_TEXT, HOME_EMPTY_TITLE, HOME_TITLE } from "./HomeEmpty";

describe("Inicio (AC-PLT-28, spec §14, 07 §2)", () => {
  it("test_AC_PLT_28_home_shows_empty_state_never_blank", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1, name: HOME_TITLE })).toBeInTheDocument();
    const empty = screen.getByRole("region", { name: HOME_EMPTY_TITLE });
    expect(empty).toHaveTextContent(HOME_EMPTY_TEXT);
  });

  it("test_AC_PLT_28_home_loading_shows_page_skeleton", () => {
    render(<HomeLoading />);
    expect(screen.getByRole("status", { name: "Cargando" })).toHaveAttribute("aria-busy", "true");
  });

  it("test_AC_PLT_28_route_error_shows_notice_with_retry", async () => {
    const reset = vi.fn();
    const internal = "relation organizations_branch does not exist";
    render(<HomeError error={new Error(internal)} reset={reset} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/Inicio/);
    // The raw error message never reaches the screen (C-08).
    expect(alert).not.toHaveTextContent(internal);
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });
});

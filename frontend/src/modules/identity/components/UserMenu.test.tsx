import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLogout } from "../hooks/useLogout";
import { useMe } from "../hooks/useMe";
import { CSRF_REFUSED, logoutResult, ME, meResult } from "./identity.test-helpers";
import { LOGOUT_LABEL, USER_MENU_LABEL, UserMenu } from "./UserMenu";

vi.mock("../hooks/useMe", () => ({ useMe: vi.fn() }));
vi.mock("../hooks/useLogout", () => ({ useLogout: vi.fn() }));

const me = vi.mocked(useMe);
const logout = vi.mocked(useLogout);

async function openMenu() {
  await userEvent.click(screen.getByRole("button", { name: USER_MENU_LABEL }));
  return screen.findByRole("menu");
}

describe("UserMenu (RF-IDA-05, spec §14, design.md §3.4)", () => {
  beforeEach(() => {
    me.mockReturnValue(meResult({ data: ME }));
    logout.mockReturnValue(logoutResult());
  });

  it("test_RF_IDA_05_user_menu_shows_who_is_signed_in", async () => {
    render(<UserMenu />);
    const menu = await openMenu();
    expect(menu).toHaveTextContent(ME.display_name);
    expect(menu).toHaveTextContent(ME.email);
    expect(LOGOUT_LABEL).toBe("Cerrar sesión");
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(1);
  });

  it("test_RF_IDA_05_user_menu_logout_calls_the_bff_logout", async () => {
    const result = logoutResult();
    logout.mockReturnValue(result);
    render(<UserMenu />);
    const menu = await openMenu();
    await userEvent.click(within(menu).getByRole("menuitem", { name: LOGOUT_LABEL }));
    expect(result.mutate).toHaveBeenCalledTimes(1);
  });

  it("test_RF_IDA_05_user_menu_logout_in_progress_is_disabled", async () => {
    logout.mockReturnValue(logoutResult({ isPending: true }));
    render(<UserMenu />);
    const menu = await openMenu();
    expect(within(menu).getByRole("menuitem", { name: LOGOUT_LABEL })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  // T-IDA-25: a refused logout left the session open; the menu says so and offers a retry.
  it("test_RF_IDA_05_user_menu_logout_403_shows_error_not_closed", async () => {
    const result = logoutResult({ isError: true, error: CSRF_REFUSED });
    logout.mockReturnValue(result);
    render(<UserMenu />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(CSRF_REFUSED.title);
    await userEvent.click(within(alert).getByRole("button", { name: "Reintentar" }));
    expect(result.mutate).toHaveBeenCalledTimes(1);
  });

  it("test_RF_IDA_05_user_menu_logout_works_without_me", async () => {
    // /api/me loading or failed: "Cerrar sesión" does not depend on it.
    me.mockReturnValue(meResult({ isPending: true }));
    render(<UserMenu />);
    const menu = await openMenu();
    expect(within(menu).getByRole("menuitem", { name: LOGOUT_LABEL })).toBeInTheDocument();
  });
});

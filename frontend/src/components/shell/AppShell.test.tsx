import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";
import { isActive, NAV_LABEL } from "./NavMenu";
import { ORG_BRANCH_PENDING_TEXT } from "./OrgBranchSelectorPlaceholder";
import { APP_TITLE, OPEN_NAV_LABEL } from "./TopBar";
import { USER_MENU_LABEL } from "./UserMenuPlaceholder";

vi.mock("next/navigation", () => ({ usePathname: vi.fn() }));

const pathname = vi.mocked(usePathname);

function renderShell() {
  return render(
    <AppShell>
      <p>contenido de la página</p>
    </AppShell>,
  );
}

describe("AppShell (AC-PLT-28, spec §14, 07 §5)", () => {
  beforeEach(() => {
    pathname.mockReturnValue("/inicio");
  });

  it("test_AC_PLT_28_top_bar_has_disabled_org_branch_selector", () => {
    renderShell();
    const bar = screen.getByRole("banner");
    expect(bar).toHaveTextContent(APP_TITLE);
    const selector = within(bar).getByRole("group", { name: "Empresa y sucursal" });
    expect(selector).toHaveAccessibleDescription(ORG_BRANCH_PENDING_TEXT);
    for (const name of ["Empresa", "Sucursal"]) {
      const select = within(selector).getByRole("combobox", { name });
      expect(select).toHaveAttribute("aria-disabled", "true");
      // No invented organizations nor branches before SPEC-02: nothing selected, no value.
      expect(select.textContent?.replace("​", "").trim()).toBe("");
    }
    expect(within(bar).getByRole("button", { name: USER_MENU_LABEL })).toBeDisabled();
  });

  it("test_AC_PLT_28_nav_links_to_inicio_and_configuracion", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: NAV_LABEL });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["Inicio", "/inicio"],
      ["Configuración", "/configuracion"],
    ]);
    expect(screen.getByRole("main")).toHaveTextContent("contenido de la página");
  });

  it("test_AC_PLT_28_active_item_follows_pathname", () => {
    pathname.mockReturnValue("/configuracion");
    const { rerender } = renderShell();
    const nav = () => screen.getByRole("navigation", { name: NAV_LABEL });
    expect(within(nav()).getByRole("link", { name: "Configuración" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav()).getByRole("link", { name: "Inicio" })).not.toHaveAttribute("aria-current");

    pathname.mockReturnValue("/inicio");
    rerender(
      <AppShell>
        <p>contenido de la página</p>
      </AppShell>,
    );
    expect(within(nav()).getByRole("link", { name: "Inicio" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav()).getByRole("link", { name: "Configuración" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("test_AC_PLT_28_active_item_matches_subroutes_only", () => {
    expect(isActive("/configuracion/integraciones", "/configuracion")).toBe(true);
    expect(isActive("/inicio-otra", "/inicio")).toBe(false);
    expect(isActive(null, "/inicio")).toBe(false);
  });

  it("test_AC_PLT_28_mobile_menu_opens_and_closes_on_navigation", async () => {
    // jsdom cannot load another document: keep the click on the link from trying to.
    const stopNavigation = (event: MouseEvent) => event.preventDefault();
    document.addEventListener("click", stopNavigation);
    renderShell();
    expect(screen.getAllByRole("navigation", { name: NAV_LABEL })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: OPEN_NAV_LABEL }));
    const dialog = await screen.findByRole("presentation");
    const mobileNav = within(dialog).getByRole("navigation", { name: NAV_LABEL });
    await userEvent.click(within(mobileNav).getByRole("link", { name: "Configuración" }));
    await vi.waitFor(() => {
      expect(screen.queryByRole("presentation")).toBeNull();
    });
    document.removeEventListener("click", stopNavigation);
  });
});

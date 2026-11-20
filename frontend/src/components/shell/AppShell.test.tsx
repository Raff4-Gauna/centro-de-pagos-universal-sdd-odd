import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { logoutResult, ME, meResult } from "@/modules/identity/components/identity.test-helpers";
import { USER_MENU_LABEL } from "@/modules/identity/components/UserMenu";
import { useLogout } from "@/modules/identity/hooks/useLogout";
import { useMe } from "@/modules/identity/hooks/useMe";
import { SUSPENDED_TEXT } from "@/modules/tenancy/components/SuspendedBanner";
import {
  ACME,
  activeOrganizationResult,
  BETA,
  organizationsResult,
} from "@/modules/tenancy/components/tenancy.test-helpers";
import { useActiveOrganization } from "@/modules/tenancy/context/ActiveOrgProvider";
import { useOrganizations } from "@/modules/tenancy/hooks/useOrganizations";

import { AppShell } from "./AppShell";
import { isActive, NAV_LABEL } from "./NavMenu";
import { APP_TITLE, OPEN_NAV_LABEL } from "./TopBar";

vi.mock("next/navigation", () => ({ usePathname: vi.fn() }));
vi.mock("@/modules/identity/hooks/useMe", () => ({ useMe: vi.fn() }));
vi.mock("@/modules/identity/hooks/useLogout", () => ({ useLogout: vi.fn() }));
vi.mock("@/modules/tenancy/hooks/useOrganizations", () => ({ useOrganizations: vi.fn() }));
vi.mock("@/modules/tenancy/context/ActiveOrgProvider", () => ({
  useActiveOrganization: vi.fn(),
}));

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
    vi.mocked(useMe).mockReturnValue(meResult({ data: ME }));
    vi.mocked(useLogout).mockReturnValue(logoutResult());
    vi.mocked(useOrganizations).mockReturnValue(organizationsResult({ data: [ACME, BETA] }));
    vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
  });

  it("test_AC_PLT_28_top_bar_has_org_branch_selector", () => {
    renderShell();
    const bar = screen.getByRole("banner");
    expect(bar).toHaveTextContent(APP_TITLE);
    const selector = within(bar).getByRole("group", { name: "Empresa y sucursal" });
    // SPEC-02 (T-TEN-29): the company selector replaces the disabled placeholder.
    expect(within(selector).getByRole("combobox", { name: "Empresa" })).toHaveTextContent(
      ACME.name,
    );
    expect(within(selector).getByRole("combobox", { name: "Sucursal" })).toBeInTheDocument();
    // SPEC-01 (T-IDA-29): the user menu replaces the disabled placeholder.
    expect(within(bar).getByRole("button", { name: USER_MENU_LABEL })).toBeEnabled();
    expect(screen.queryByText(SUSPENDED_TEXT)).not.toBeInTheDocument();
  });

  it("test_RF_TEN_02_shell_shows_banner_for_a_suspended_company", () => {
    vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(BETA.id));
    renderShell();
    expect(within(screen.getByRole("main")).getByRole("alert")).toHaveTextContent(SUSPENDED_TEXT);
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
    // The drawer is not kept mounted: closed, a single nav is left (the avatar's decorative image
    // also has the presentation role, so the drawer is matched by its nav, not by that role).
    await vi.waitFor(() => {
      expect(screen.getAllByRole("navigation", { name: NAV_LABEL })).toHaveLength(1);
    });
    document.removeEventListener("click", stopNavigation);
  });
});

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SettingsError from "@/app/(dashboard)/configuracion/error";
import SettingsLoading from "@/app/(dashboard)/configuracion/loading";
import SettingsPage from "@/app/(dashboard)/configuracion/page";

import { moduleChipLabel } from "../settings-sections";
import { SETTINGS_LIST_LABEL, SETTINGS_TITLE } from "./SettingsSectionList";

// 07 §5.3: each section of the Hub with the chip of the module that implements it.
const EXPECTED = [
  ["Mi perfil", "Módulo 01"],
  ["Seguridad", "Módulo 01"],
  ["Colaboradores", "Módulo 02"],
  ["Datos de la empresa", "Módulo 02"],
  ["Sucursales y cajas", "Módulos 02 y 05"],
  ["Integraciones", "Módulo 04"],
  ["Costos y comisiones", "Módulo 08"],
  ["Dispositivos", "Módulos 12 y 14"],
  ["API / Puente ERP", "Módulo 11"],
] as const;

describe("Configuración (AC-PLT-28, spec §14, 07 §5.3)", () => {
  it("test_AC_PLT_28_settings_lists_nine_sections_disabled_with_module_chip", () => {
    render(<SettingsPage />);
    expect(screen.getByRole("heading", { level: 1, name: SETTINGS_TITLE })).toBeInTheDocument();
    const list = screen.getByRole("list", { name: SETTINGS_LIST_LABEL });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(9);
    items.forEach((item, index) => {
      const [title, chip] = EXPECTED[index];
      expect(item).toHaveAccessibleName(title);
      expect(item).toHaveAttribute("aria-disabled", "true");
      expect(item).toHaveTextContent(chip);
      // Disabled means nothing to activate: no links nor buttons inside a section.
      expect(within(item).queryByRole("link")).toBeNull();
      expect(within(item).queryByRole("button")).toBeNull();
    });
  });

  it("test_AC_PLT_28_settings_module_chip_label_joins_modules", () => {
    expect(moduleChipLabel(["04"])).toBe("Módulo 04");
    expect(moduleChipLabel(["02", "05"])).toBe("Módulos 02 y 05");
    expect(moduleChipLabel(["01", "02", "05"])).toBe("Módulos 01, 02 y 05");
  });

  it("test_AC_PLT_28_settings_loading_shows_page_skeleton", () => {
    render(<SettingsLoading />);
    const status = screen.getByRole("status", { name: "Cargando" });
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("data-variant", "table");
  });

  it("test_AC_PLT_28_settings_route_error_shows_retry", async () => {
    const reset = vi.fn();
    const internal = "relation integrations_integration does not exist";
    render(<SettingsError error={new Error(internal)} reset={reset} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/Configuración/);
    // The raw error message never reaches the screen (C-08).
    expect(alert).not.toHaveTextContent(internal);
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });
});

import type { TenancyAction } from "@/modules/tenancy/hooks/useCurrentOrganizationDetails";

// Sections of Configuración (07 §5.3, design.md §3.3.2). A section without `href` does not work
// yet: it is listed disabled with the module that implements it, so the screen is never blank and
// nothing is invented. A module enables its own section, with the route of its page, when it ships.
// A section with `requires` is listed only when the active company's `allowed_actions` bring that
// action (design.md §3.9: "Colaboradores" is hidden from operator and viewer); a direct visit still
// gets the page's "sin permiso" state, because the backend decides.
export type SettingsSection = Readonly<{
  id: string;
  title: string;
  description: string;
  // Module numbers (specs/NN-*) that implement the section, in order.
  modules: readonly string[];
  href?: string;
  requires?: TenancyAction;
}>;

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  {
    id: "profile",
    title: "Mi perfil",
    description: "Tus datos personales: nombre y email.",
    modules: ["01"],
    href: "/configuracion/perfil",
  },
  {
    id: "security",
    title: "Seguridad",
    description: "Sesiones activas y cierre de sesiones.",
    modules: ["01"],
    href: "/configuracion/seguridad",
  },
  {
    id: "members",
    title: "Colaboradores",
    description: "Miembros de la empresa, su rol e invitaciones por email.",
    modules: ["02"],
    href: "/configuracion/colaboradores",
    requires: "member.list",
  },
  {
    id: "company",
    title: "Datos de la empresa",
    description: "Razón social, rubro y datos fiscales que el Hub necesita.",
    modules: ["02"],
  },
  {
    id: "branches",
    title: "Sucursales y cajas",
    description: "Alta y edición de sucursales y de sus cajas por integración.",
    modules: ["02", "05"],
    href: "/configuracion/sucursales",
  },
  {
    id: "integrations",
    title: "Integraciones",
    description: "Alta y baja de integraciones por proveedor, credenciales y prueba de conexión.",
    modules: ["04"],
  },
  {
    id: "fees",
    title: "Costos y comisiones",
    description: "Solo informativo: lo que cobra de comisión cada proveedor.",
    modules: ["08"],
  },
  {
    id: "devices",
    title: "Dispositivos",
    description: "Terminales y dispositivos de cobro vinculados.",
    modules: ["12", "14"],
  },
  {
    id: "erp-bridge",
    title: "API / Puente ERP",
    description: "Claves de API con alcance para que tu ERP consuma el Hub.",
    modules: ["11"],
  },
];

// Text of the module chip: "Módulo 01", "Módulos 02 y 05", "Módulos 01, 02 y 05".
export function moduleChipLabel(modules: readonly string[]): string {
  if (modules.length === 1) return `Módulo ${modules[0]}`;
  const head = modules.slice(0, -1).join(", ");
  return `Módulos ${head} y ${modules[modules.length - 1]}`;
}

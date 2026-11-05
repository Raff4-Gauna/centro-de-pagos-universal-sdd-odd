// Sections of Configuración (07 §5.3, design.md §3.3.2). In 00-platform none of them works yet:
// each one is listed disabled with the module that implements it, so the screen is never blank
// and nothing is invented. A module enables its own section when it ships.
export type SettingsSection = Readonly<{
  id: string;
  title: string;
  description: string;
  // Module numbers (specs/NN-*) that implement the section, in order.
  modules: readonly string[];
}>;

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  {
    id: "profile",
    title: "Mi perfil",
    description: "Tus datos personales: nombre, email e idioma.",
    modules: ["01"],
  },
  {
    id: "security",
    title: "Seguridad",
    description: "Sesiones activas y cierre de sesiones.",
    modules: ["01"],
  },
  {
    id: "members",
    title: "Colaboradores",
    description: "Miembros de la empresa, su rol e invitaciones por email.",
    modules: ["02"],
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

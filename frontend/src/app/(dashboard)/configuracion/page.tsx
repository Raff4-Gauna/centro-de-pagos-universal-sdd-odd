import type { Metadata } from "next";

import { SettingsSectionList } from "@/modules/settings/components/SettingsSectionList";

export const metadata: Metadata = { title: "Configuración | Centro de Pagos Universal" };

export default function SettingsPage() {
  return <SettingsSectionList />;
}

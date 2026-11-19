import type { Metadata } from "next";

import { SecurityScreen } from "@/modules/identity/components/SessionsTable";

export const metadata: Metadata = { title: "Seguridad | Centro de Pagos Universal" };

export default function SecurityPage() {
  return <SecurityScreen />;
}

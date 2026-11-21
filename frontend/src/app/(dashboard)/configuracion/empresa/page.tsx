import type { Metadata } from "next";

import { CompanyScreen } from "@/modules/tenancy/components/CompanyScreen";

export const metadata: Metadata = { title: "Datos de la empresa | Centro de Pagos Universal" };

export default function CompanyPage() {
  return <CompanyScreen />;
}

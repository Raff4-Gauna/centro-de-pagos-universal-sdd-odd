import type { Metadata } from "next";

import { BranchesScreen } from "@/modules/tenancy/components/BranchesTable";

export const metadata: Metadata = { title: "Sucursales | Centro de Pagos Universal" };

export default function BranchesPage() {
  return <BranchesScreen />;
}

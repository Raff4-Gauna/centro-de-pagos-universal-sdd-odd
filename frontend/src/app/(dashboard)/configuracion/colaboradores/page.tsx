import type { Metadata } from "next";

import { MembersScreen } from "@/modules/tenancy/components/MembersScreen";

export const metadata: Metadata = { title: "Colaboradores | Centro de Pagos Universal" };

export default function MembersPage() {
  return <MembersScreen />;
}

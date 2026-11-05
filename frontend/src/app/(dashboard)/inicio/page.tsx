import type { Metadata } from "next";

import { HomeEmpty } from "@/modules/home/components/HomeEmpty";

export const metadata: Metadata = { title: "Inicio | Centro de Pagos Universal" };

export default function HomePage() {
  return <HomeEmpty />;
}

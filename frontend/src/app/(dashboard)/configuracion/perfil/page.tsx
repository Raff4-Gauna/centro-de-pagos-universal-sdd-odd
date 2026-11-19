import type { Metadata } from "next";

import { ProfileCard } from "@/modules/identity/components/ProfileCard";

export const metadata: Metadata = { title: "Mi perfil | Centro de Pagos Universal" };

export default function ProfilePage() {
  return <ProfileCard />;
}

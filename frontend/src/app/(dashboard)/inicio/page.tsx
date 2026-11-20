import type { Metadata } from "next";

import { HomeEmpty } from "@/modules/home/components/HomeEmpty";
import { PendingInvitationsNotice } from "@/modules/tenancy/components/PendingInvitationsNotice";

export const metadata: Metadata = { title: "Inicio | Centro de Pagos Universal" };

// Inicio (SPEC-00 spec §14) followed by the person's pending invitations (SPEC-02 spec §14, Q-121,
// Q-124): a member of one company may be invited to another and accepts it from here. Without
// invitations the notice renders nothing.
export default function HomePage() {
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <HomeEmpty />
      <PendingInvitationsNotice />
    </div>
  );
}

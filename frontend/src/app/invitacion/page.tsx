import type { Metadata } from "next";
import { headers } from "next/headers";

import { COOKIE_NAMES } from "@/lib/server/cookies";
import { requestCookieValues } from "@/lib/server/csrf";
import { AcceptInvitation } from "@/modules/tenancy/components/AcceptInvitation";

export const metadata: Metadata = { title: "Aceptar invitación | Centro de Pagos Universal" };

// "Aceptar invitación" (spec §14, AC-TEN-17, design.md §3.9), outside `(dashboard)`: a person who
// joins their first company has no shell yet. proxy.ts lets this page through without a session,
// because the token is in the fragment, which no redirect of the server can keep: the page itself
// stores it and sends the person to "Ingresar". The page reads the session cookie the same way
// proxy.ts does (exactly one `__Host-cpu_rt`) and only to choose between the two; the session is
// Django's call on `POST /api/invitations/accept/`. Read on every request, never in the build.
export default async function InvitationPage() {
  const hasSession = requestCookieValues(await headers(), COOKIE_NAMES.refresh).length === 1;
  return <AcceptInvitation hasSession={hasSession} />;
}

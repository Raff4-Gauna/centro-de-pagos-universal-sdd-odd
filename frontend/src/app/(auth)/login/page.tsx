import type { Metadata } from "next";

import { appOriginOrNull } from "@/lib/server/login-flow";
import { returnUrl } from "@/lib/server/return-path";
import { LoginCard } from "@/modules/identity/components/LoginCard";
import { loginErrorCodeOf } from "@/modules/identity/lib/login-errors";

export const metadata: Metadata = { title: "Ingresar | Centro de Pagos Universal" };

const START_PATH = "/api/auth/google/start";

type SearchParams = Record<string, string | string[] | undefined>;

// "Ingresar" (spec §14, design.md §3.4, AC-IDA-19). Server Component: it reads `error` and
// `return_to` from the URL and hands the card only an allowlisted code and the start link. A
// person with a session can open it too; the callback ends the previous session (ADR-0004 §13).
//
// The start link carries `return_to` only after `returnUrl` (lib/server/return-path.ts): a hostile
// value becomes "Inicio" here already, and the BFF checks it again before and after Django. A
// repeated parameter or a missing app origin leave it out.
function startHref(raw: string | string[] | undefined): string {
  const appOrigin = appOriginOrNull();
  if (typeof raw !== "string" || appOrigin === null) {
    return START_PATH;
  }
  const back = returnUrl(raw, appOrigin);
  const query = new URLSearchParams({ return_to: `${back.pathname}${back.search}` });
  return `${START_PATH}?${query.toString()}`;
}

export default async function LoginPage({
  searchParams,
}: Readonly<{ searchParams: Promise<SearchParams> }>) {
  const params = await searchParams;
  return (
    <LoginCard startHref={startHref(params.return_to)} error={loginErrorCodeOf(params.error)} />
  );
}

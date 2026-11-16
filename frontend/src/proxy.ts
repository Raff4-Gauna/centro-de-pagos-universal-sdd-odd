import { NextResponse, type NextRequest } from "next/server";

import { COOKIE_NAMES } from "@/lib/server/cookies";
import { LOGIN_PAGE_PATH, appOriginOrNull, readCookie } from "@/lib/server/login-flow";
import { returnUrl } from "@/lib/server/return-path";

// Pages need a session (design.md §3.2, spec §14, AC-IDA-19). Fail closed: every page is
// protected, the root included, except "Ingresar"; a new page is protected without touching this
// file. A request without exactly one `__Host-cpu_rt` cookie goes to `/login?return_to=<page>`
// before any API call. The cookie is only a hint: whether the session is alive is Django's call on
// the next `/api/*` request, and a dead one ends in "Ingresar" through the api-client's `401`.
//
// Left alone: `/api/*` (the BFF answers `401` itself; a redirect would hand the api-client an HTML
// page) and Next's own `/_next/*`. "Ingresar" is open with a session too.
//
// The `Location` is the absolute URL of "Ingresar" on the app origin, never built from the `Host`
// of the request. `return_to` is the page after `returnUrl` (lib/server/return-path.ts), so a
// path like `/..//evil.example` becomes "Inicio". Without a valid app origin it still redirects,
// to the fixed path `/login` with nothing from the request.

const PASS_THROUGH_PREFIXES = ["/api/", "/_next/"];

function isPublic(pathname: string): boolean {
  return (
    pathname === LOGIN_PAGE_PATH ||
    PASS_THROUGH_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  );
}

function loginLocation(request: NextRequest): string {
  const appOrigin = appOriginOrNull();
  if (appOrigin === null) {
    return LOGIN_PAGE_PATH;
  }
  const { pathname, search } = request.nextUrl;
  const back = returnUrl(`${pathname}${search}`, appOrigin);
  const query = new URLSearchParams({ return_to: `${back.pathname}${back.search}` });
  return new URL(`${LOGIN_PAGE_PATH}?${query.toString()}`, appOrigin).href;
}

export function proxy(request: NextRequest): Response {
  if (isPublic(request.nextUrl.pathname) || readCookie(request, COOKIE_NAMES.refresh) !== null) {
    return NextResponse.next();
  }
  return new Response(null, {
    status: 302,
    headers: { location: loginLocation(request), "cache-control": "no-store" },
  });
}

// Static files skip the proxy; everything else is decided above, where it is tested. Anchored, so
// `/favicon.icoX` is a page like any other and needs a session, and `/_next/staticX` reaches the
// code above (which leaves Next's own `/_next/*` alone). A literal: Next reads `config` at build
// time and ignores a variable.
export const config = {
  matcher: ["/((?!_next/static/|_next/image$|favicon\\.ico$).*)"],
};

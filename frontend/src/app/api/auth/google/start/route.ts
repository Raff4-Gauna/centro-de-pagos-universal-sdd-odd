// GET /api/auth/google/start?return_to= (RF-IDA-01, design.md §4.1, §6.3): starts a login with
// Google. Django creates the attempt (`state`, `nonce`, PKCE) bound to the login binding this
// handler keeps in `__Host-cpu_login`, and returns Google's authorization URL; the browser is sent
// there with a `302`. The binding of a previous attempt still in the cookie is reused (double
// click, two tabs), so both attempts can finish. `return_to` goes to Django already sanitized
// (django.ts, AC-IDA-19). On any failure: `302 /login?error=<code>`, with a code of the allowlist.
import { COOKIE_NAMES, loginCookie, randomCookieToken } from "@/lib/server/cookies";
import { clientIpOf } from "@/lib/server/client-ip";
import { callDjangoBff } from "@/lib/server/django";
import {
  type LoginErrorCode,
  appOriginOrNull,
  isLoginBinding,
  loginErrorCode,
  loginErrorRedirect,
  loginRedirect,
  problemCodeOf,
  readCookie,
} from "@/lib/server/login-flow";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/server/request-id";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALLOWED_PROTOCOLS = new Set(["https:", "http:"]);

// Google's URL (or the fake provider's in dev) as Django built it; anything else is a failure.
async function authorizationUrlOf(response: Response): Promise<URL | null> {
  try {
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null || !("authorization_url" in body)) {
      return null;
    }
    const raw = body.authorization_url;
    if (typeof raw !== "string") {
      return null;
    }
    const url = new URL(raw);
    return ALLOWED_PROTOCOLS.has(url.protocol) ? url : null;
  } catch {
    return null;
  }
}

export async function GET(request: Request): Promise<Response> {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  // Checked first: without it, the callback could not redirect back into the app.
  const appOrigin = appOriginOrNull();
  const fail = (code: LoginErrorCode) => loginErrorRedirect(code, appOrigin, requestId);
  if (appOrigin === null) {
    return fail("internal_error");
  }

  let clientIp: string | null;
  try {
    clientIp = clientIpOf(request);
  } catch {
    return fail("internal_error");
  }

  const previous = readCookie(request, COOKIE_NAMES.login);
  const binding = isLoginBinding(previous) ? previous : randomCookieToken();
  const returnTo = new URL(request.url).searchParams.get("return_to");
  const outcome = await callDjangoBff({
    path: "/api/auth/bff/login/start/",
    body:
      returnTo === null
        ? { login_binding: binding }
        : { login_binding: binding, return_path: returnTo },
    requestId,
    clientIp,
    signal: request.signal,
  });
  if (outcome.kind === "unavailable") {
    return fail("internal_error");
  }

  const { response } = outcome;
  if (response.status !== 200) {
    return fail(loginErrorCode(await problemCodeOf(response)));
  }
  const authorizationUrl = await authorizationUrlOf(response);
  if (authorizationUrl === null) {
    return fail("internal_error");
  }
  return loginRedirect(authorizationUrl.href, requestId, [loginCookie(binding)]);
}

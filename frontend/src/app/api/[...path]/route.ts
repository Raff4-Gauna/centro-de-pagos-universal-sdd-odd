// /api/{path...} (RF-PLT-06): the BFF catch-all. The browser only talks to this same-origin
// handler (Q-050); everything is delegated to the server-only proxy in lib/server, which adds the
// session (Bearer, CSRF, refresh: session-proxy.ts) to the pass-through of backend-proxy.ts.
// `/api/health` and the `api/auth/*` and `api/session/*` routes are static and take precedence.
import { proxyWithSession } from "@/lib/server/session-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(request: Request, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  return proxyWithSession(request, path);
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST, handle as PUT };

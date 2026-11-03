// /api/{path...} (RF-PLT-06): the BFF catch-all. The browser only talks to this same-origin
// handler (Q-050); everything is delegated to the server-only pass-through in lib/server.
// `/api/health` is a static route and takes precedence over this one.
import { proxyToBackend } from "@/lib/server/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(request: Request, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  return proxyToBackend(request, path);
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST, handle as PUT };

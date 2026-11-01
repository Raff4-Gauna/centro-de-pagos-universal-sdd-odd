// GET /api/health (RF-PLT-07): liveness of the frontend/BFF process only. It never calls the
// backend, so a backend outage shows up in the backend's /readyz, not here.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}

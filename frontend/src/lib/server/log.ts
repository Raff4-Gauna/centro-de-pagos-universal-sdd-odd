import "server-only";

// Structured logger of the BFF (RF-PLT-06, C-16): one JSON object per line on stdout. It logs the
// route template only, never the raw path or the query string (they can carry semi-secret IDs or
// tokens: Q-041, C-06), and never headers or bodies.
export const BFF_ROUTE_TEMPLATE = "/api/[...path]";

export type BffRequestLog = {
  requestId: string;
  method: string;
  status: number;
  // Measured until the response headers are available (upstream headers, or the BFF's own
  // problem response); streaming the body afterwards is not included.
  durationMs: number;
  // Only on the BFF's own problem responses (`bff.bad_path`, `bff.upstream_*`).
  code?: string;
};

export function logBffRequest({
  requestId,
  method,
  status,
  durationMs,
  code,
}: BffRequestLog): void {
  const line = JSON.stringify({
    timestamp: new Date().toISOString(),
    level: status >= 500 ? "error" : "info",
    component: "bff",
    event: "bff.request",
    request_id: requestId,
    method,
    route: BFF_ROUTE_TEMPLATE,
    status,
    duration_ms: Math.round(durationMs),
    code, // dropped by JSON.stringify when undefined
  });
  process.stdout.write(`${line}\n`);
}

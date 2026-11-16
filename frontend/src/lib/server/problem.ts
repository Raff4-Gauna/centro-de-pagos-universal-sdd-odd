import "server-only";

import { REQUEST_ID_HEADER } from "./request-id";

// problem+json responses the BFF writes itself for the session routes of SPEC-01 (design.md §6.3,
// §7.2), in the envelope of SPEC-00 (RN-PLT-15): `type`, `title`, `status`, a stable `code` with
// the `bff.` prefix of the BFF's own codes (00 design.md §6.2) and the `request_id`. Never cached
// and never with a `detail` on a 5xx: the cause (backend URL, network error) stays out (C-06).
// `not_found`, `session_revoked` and `rate_limited` are Django's own codes, unprefixed on purpose:
// the session proxy answers them in Django's place (design.md §6.3) and the api-client and screens
// must not tell the two apart (a denied route looks like a missing one).
export type BffProblemCode =
  | "bff.csrf_failed"
  | "bff.upstream_unavailable"
  | "bff.upstream_timeout"
  | "not_found"
  | "session_revoked"
  | "rate_limited";

const PROBLEMS: Record<BffProblemCode, { status: number; title: string; detail?: string }> = {
  "bff.csrf_failed": {
    status: 403,
    title: "Solicitud rechazada",
    detail: "La solicitud no pasó la verificación de origen. Recargá la página e intentá de nuevo.",
  },
  not_found: { status: 404, title: "No encontrado" },
  session_revoked: {
    status: 401,
    title: "Sesión finalizada",
    detail: "Tu sesión terminó. Ingresá de nuevo para continuar.",
  },
  rate_limited: { status: 429, title: "Demasiadas solicitudes" },
  "bff.upstream_unavailable": { status: 502, title: "Servicio no disponible" },
  "bff.upstream_timeout": { status: 504, title: "El servicio no respondió a tiempo" },
};

export function bffProblem(code: BffProblemCode, requestId: string): Response {
  const { status, title, detail } = PROBLEMS[code];
  const body = {
    type: `urn:hub:problem:${code}`,
    title,
    status,
    code,
    detail,
    request_id: requestId,
  };
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/problem+json",
      "cache-control": "no-store",
      [REQUEST_ID_HEADER]: requestId,
    },
  });
}

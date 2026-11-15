// PUT /api/session/active-organization (Q-112, Q-119 b, ADR-0004 §7, design.md §6.3, §7.2): keeps the
// last organization the person picked in the `HttpOnly` cookie `__Host-cpu_org`, the initial value
// for new tabs and reloads (the `(dashboard)` layout reads it on the server). Body
// `{organization_id: uuid | null}`; `null` clears the cookie. Answer: a bodiless `204`.
//
// A preference, not an authorization: only the format is checked and Django is not asked. Each tab
// sends its own organization in `X-Organization-Id` and SPEC-02 revalidates the membership on every
// request, so a cookie naming an organization the person does not belong to opens nothing.
//
// CSRF (RN-IDA-13, design.md §7.2): Origin and double submit before anything else; a refusal is
// `403 bff.csrf_failed` and no cookie is written. A body that is not a small JSON object is
// `400 parse_error`; a missing or malformed `organization_id`, `400 validation_error` with
// `errors[]`, in the envelope and with the titles of SPEC-00's catalog (00 design.md §6.2). The value
// sent is never echoed in the answer.
import {
  clearedCookie,
  COOKIE_NAMES,
  organizationCookie,
  serializeCookie,
} from "@/lib/server/cookies";
import { checkCsrf, csrfFailure } from "@/lib/server/csrf";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/server/request-id";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FIELD = "organization_id";
// `{"organization_id":"<36>"}` is 55 bytes: this leaves room for whitespace and nothing else.
const MAX_BODY_BYTES = 1024;
// Canonical hyphenated form (RFC 9562), any version: the organization's id as Django stores it.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type FieldError = { field: string; code: "required" | "invalid"; message: string };

type Selection = { kind: "set"; organizationId: string } | { kind: "clear" };

type Parsed =
  | { ok: true; selection: Selection }
  | { ok: false; code: "parse_error" }
  | { ok: false; code: "validation_error"; error: FieldError };

const TITLES = { parse_error: "Solicitud mal formada", validation_error: "Datos inválidos" };

// The body up to `MAX_BODY_BYTES`, or null if it is longer: an oversized body is never buffered whole.
async function boundedText(request: Request): Promise<string | null> {
  if (request.body === null) {
    return "";
  }
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks));
}

function parseSelection(body: unknown): Parsed {
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return { ok: false, code: "parse_error" };
  }
  if (!(FIELD in body)) {
    const message = "Este campo es obligatorio.";
    return {
      ok: false,
      code: "validation_error",
      error: { field: FIELD, code: "required", message },
    };
  }
  const value = (body as Record<string, unknown>)[FIELD];
  if (value === null) {
    return { ok: true, selection: { kind: "clear" } };
  }
  if (typeof value !== "string" || !UUID.test(value)) {
    const message = "Debe ser un UUID válido.";
    return {
      ok: false,
      code: "validation_error",
      error: { field: FIELD, code: "invalid", message },
    };
  }
  return { ok: true, selection: { kind: "set", organizationId: value.toLowerCase() } };
}

async function parseRequest(request: Request): Promise<Parsed> {
  let body: unknown;
  try {
    const text = await boundedText(request);
    if (text === null) {
      return { ok: false, code: "parse_error" };
    }
    body = JSON.parse(text);
  } catch {
    // Empty, not UTF-8 or not JSON.
    return { ok: false, code: "parse_error" };
  }
  return parseSelection(body);
}

function badRequest(parsed: Exclude<Parsed, { ok: true }>, requestId: string): Response {
  const { code } = parsed;
  const body = {
    type: `urn:hub:problem:${code}`,
    title: TITLES[code],
    status: 400,
    code,
    request_id: requestId,
    ...(parsed.code === "validation_error" ? { errors: [parsed.error] } : {}),
  };
  return new Response(JSON.stringify(body), {
    status: 400,
    headers: {
      "content-type": "application/problem+json",
      "cache-control": "no-store",
      [REQUEST_ID_HEADER]: requestId,
    },
  });
}

export async function PUT(request: Request): Promise<Response> {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const refused = csrfFailure(checkCsrf(request), requestId);
  if (refused !== null) {
    return refused;
  }

  const parsed = await parseRequest(request);
  if (!parsed.ok) {
    return badRequest(parsed, requestId);
  }
  const { selection } = parsed;
  const cookie =
    selection.kind === "set"
      ? organizationCookie(selection.organizationId)
      : clearedCookie(COOKIE_NAMES.organization);
  return new Response(null, {
    status: 204,
    headers: {
      "cache-control": "no-store",
      "set-cookie": serializeCookie(cookie),
      [REQUEST_ID_HEADER]: requestId,
    },
  });
}

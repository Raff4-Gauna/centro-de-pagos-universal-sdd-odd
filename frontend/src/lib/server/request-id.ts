import "server-only";

// X-Request-ID rule shared with the backend (RN-PLT-07, Q-041): an incoming value is accepted only
// if it is exactly 36 characters and fully matches a UUIDv4 (case-insensitive). `^...$` without
// the `m` flag anchors the whole string, so a trailing newline does not pass. Anything else is
// discarded and a fresh UUIDv4 is generated, which keeps arbitrary input out of the logs.
export const REQUEST_ID_HEADER = "x-request-id";

const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseRequestId(value: string | null | undefined): string | null {
  if (typeof value !== "string" || value.length !== 36 || !UUID4.test(value)) {
    return null;
  }
  return value;
}

export function resolveRequestId(incoming: string | null | undefined): string {
  return parseRequestId(incoming) ?? crypto.randomUUID();
}

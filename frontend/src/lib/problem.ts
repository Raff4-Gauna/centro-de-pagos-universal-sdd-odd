import type { components } from "@/types/api";

// Error envelope of the API (RN-PLT-15, design.md §6.2, ADR-0005): `application/problem+json`
// (RFC 9457) with a stable `code` and the `request_id`. The shape comes from the generated
// contract types, never from a hand-written DTO. The client turns every failed response into one
// `ApiError`, and only keeps what the UI may show: the fixed `title`, the plain-text `detail` of a
// 4xx (never of a 5xx), the field errors and the request id to quote to support. The raw body,
// the response headers and any network error stay out of it.

export type Problem = components["schemas"]["Problem"];
export type ProblemFieldError = components["schemas"]["ProblemFieldError"];

export const PROBLEM_CONTENT_TYPE = "application/problem+json";

const REQUEST_ID_HEADER = "x-request-id";

// Codes the browser assigns when there is no problem+json to read. They never come from the
// backend (its codes have no `client.` prefix), so a screen can tell them apart.
export const CLIENT_ERROR_CODES = {
  unexpectedResponse: "client.unexpected_response",
  network: "client.network_error",
} as const;

const UNEXPECTED_RESPONSE_TITLE = "Respuesta inesperada del servidor";
const NETWORK_ERROR_TITLE = "No se pudo conectar con el servidor";

export type ApiErrorInit = Readonly<{
  status: number;
  code: string;
  title: string;
  detail?: string;
  requestId: string | null;
  fieldErrors?: readonly ProblemFieldError[];
}>;

export class ApiError extends Error {
  override readonly name = "ApiError";
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string | undefined;
  readonly requestId: string | null;
  readonly fieldErrors: readonly ProblemFieldError[];

  constructor(init: ApiErrorInit) {
    // The message is the fixed title of the code: safe to log or show, it carries no input.
    super(init.title);
    this.status = init.status;
    this.code = init.code;
    this.title = init.title;
    // `detail` is never part of a 5xx (design.md §6.2), even if a body brought one.
    this.detail = init.status >= 500 ? undefined : init.detail;
    this.requestId = init.requestId;
    this.fieldErrors = init.fieldErrors ?? [];
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFieldError(value: unknown): value is ProblemFieldError {
  return (
    isRecord(value) &&
    typeof value.field === "string" &&
    typeof value.code === "string" &&
    typeof value.message === "string"
  );
}

// Runtime check of a body against the `Problem` component: required members with their types,
// `status` an integer in 400-599. Malformed field errors are dropped, not trusted.
export function parseProblem(value: unknown): Problem | null {
  if (!isRecord(value)) {
    return null;
  }
  const { type, title, status, code, detail, request_id: requestId, errors } = value;
  if (
    typeof type !== "string" ||
    typeof title !== "string" ||
    typeof code !== "string" ||
    typeof status !== "number" ||
    !Number.isInteger(status) ||
    status < 400 ||
    status > 599 ||
    (requestId !== null && typeof requestId !== "string") ||
    (detail !== undefined && typeof detail !== "string")
  ) {
    return null;
  }
  const problem: Problem = { type, title, status, code, request_id: requestId };
  if (detail !== undefined) {
    problem.detail = detail;
  }
  if (Array.isArray(errors)) {
    problem.errors = errors.filter(isFieldError);
  }
  return problem;
}

export function isProblemResponse(response: Response): boolean {
  const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  return mediaType === PROBLEM_CONTENT_TYPE;
}

async function readProblem(response: Response): Promise<Problem | null> {
  if (!isProblemResponse(response)) {
    return null;
  }
  try {
    return parseProblem(await response.json());
  } catch {
    return null;
  }
}

// Every non-2xx response becomes an `ApiError`. The HTTP status of the response is the one kept;
// a body that is not a valid problem+json yields the generic client code, without its content.
export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const headerRequestId = response.headers.get(REQUEST_ID_HEADER);
  const problem = await readProblem(response);
  if (problem === null) {
    return new ApiError({
      status: response.status,
      code: CLIENT_ERROR_CODES.unexpectedResponse,
      title: UNEXPECTED_RESPONSE_TITLE,
      requestId: headerRequestId,
    });
  }
  return new ApiError({
    status: response.status,
    code: problem.code,
    title: problem.title,
    detail: problem.detail,
    requestId: problem.request_id ?? headerRequestId,
    fieldErrors: problem.errors,
  });
}

// The request never got a response (BFF unreachable, connection cut). Status 0, like a failed
// `fetch`; the underlying error is not kept.
export function networkApiError(): ApiError {
  return new ApiError({
    status: 0,
    code: CLIENT_ERROR_CODES.network,
    title: NETWORK_ERROR_TITLE,
    requestId: null,
  });
}

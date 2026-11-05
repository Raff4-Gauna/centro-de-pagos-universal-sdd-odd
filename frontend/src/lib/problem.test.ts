import { describe, expect, it } from "vitest";

import {
  ApiError,
  apiErrorFromResponse,
  CLIENT_ERROR_CODES,
  isProblemResponse,
  networkApiError,
  parseProblem,
  type Problem,
} from "./problem";

const REQUEST_ID = "9b1d6f0e-3c2a-4b8e-9f1d-2a7c5e4b3d10";

function problemResponse(body: unknown, status: number, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });
}

const validationProblem: Problem = {
  type: "urn:hub:problem:validation_error",
  title: "Datos inválidos",
  status: 400,
  code: "validation_error",
  detail: "Revisá los campos marcados.",
  request_id: REQUEST_ID,
  errors: [{ field: "amount", code: "required", message: "Este campo es obligatorio." }],
};

describe("problem+json to ApiError (AC-PLT-23, design.md §6.2)", () => {
  it("test_AC_PLT_23_problem_json_becomes_api_error", async () => {
    const error = await apiErrorFromResponse(problemResponse(validationProblem, 400));

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toBeInstanceOf(Error);
    expect(error).toMatchObject({
      name: "ApiError",
      message: "Datos inválidos",
      status: 400,
      code: "validation_error",
      title: "Datos inválidos",
      detail: "Revisá los campos marcados.",
      requestId: REQUEST_ID,
      fieldErrors: [{ field: "amount", code: "required", message: "Este campo es obligatorio." }],
    });
  });

  it("test_AC_PLT_23_5xx_problem_never_carries_detail", async () => {
    const body = {
      type: "urn:hub:problem:internal_error",
      title: "Error interno",
      status: 500,
      code: "internal_error",
      detail: "Traceback (most recent call last): db.internal:5432",
      request_id: REQUEST_ID,
    };
    const error = await apiErrorFromResponse(problemResponse(body, 500));

    expect(error.code).toBe("internal_error");
    expect(error.detail).toBeUndefined();
    expect(JSON.stringify(error)).not.toContain("db.internal");
    expect(error.message).not.toContain("Traceback");
  });

  it("test_AC_PLT_23_missing_request_id_falls_back_to_the_header", async () => {
    const body = { ...validationProblem, request_id: null };
    const error = await apiErrorFromResponse(
      problemResponse(body, 400, { "x-request-id": REQUEST_ID }),
    );
    expect(error.requestId).toBe(REQUEST_ID);
  });

  it("test_AC_PLT_23_response_status_wins_over_body_status", async () => {
    const error = await apiErrorFromResponse(problemResponse({ ...validationProblem }, 422));
    expect(error.status).toBe(422);
  });

  it("test_AC_PLT_23_media_type_parameters_and_case_are_accepted", () => {
    const response = new Response("{}", {
      headers: { "content-type": "Application/Problem+JSON; charset=utf-8" },
    });
    expect(isProblemResponse(response)).toBe(true);
    expect(isProblemResponse(new Response("{}"))).toBe(false);
  });

  it("test_AC_PLT_23_non_problem_error_body_is_not_exposed", async () => {
    const response = new Response("<html>nginx at 10.0.0.7 internal</html>", {
      status: 502,
      headers: { "content-type": "text/html", "x-request-id": REQUEST_ID },
    });
    const error = await apiErrorFromResponse(response);

    expect(error).toMatchObject({
      status: 502,
      code: CLIENT_ERROR_CODES.unexpectedResponse,
      requestId: REQUEST_ID,
      fieldErrors: [],
    });
    expect(error.detail).toBeUndefined();
    expect(JSON.stringify(error) + error.message).not.toContain("10.0.0.7");
  });

  it("test_AC_PLT_23_problem_media_type_with_invalid_body_is_unexpected", async () => {
    const notJson = new Response("not json", {
      status: 400,
      headers: { "content-type": "application/problem+json" },
    });
    expect((await apiErrorFromResponse(notJson)).code).toBe(CLIENT_ERROR_CODES.unexpectedResponse);

    const wrongShape = problemResponse({ code: "validation_error" }, 400);
    const error = await apiErrorFromResponse(wrongShape);
    expect(error.code).toBe(CLIENT_ERROR_CODES.unexpectedResponse);
    expect(error.requestId).toBeNull();
  });

  it("test_AC_PLT_23_network_error_has_fixed_code_and_no_cause", () => {
    const error = networkApiError();
    expect(error).toMatchObject({ status: 0, code: CLIENT_ERROR_CODES.network, requestId: null });
    expect(error.cause).toBeUndefined();
  });
});

describe("parseProblem (Problem component of the contract)", () => {
  it.each([
    ["not an object", "oops"],
    ["an array", [validationProblem]],
    ["null", null],
    ["status out of range", { ...validationProblem, status: 302 }],
    ["status not an integer", { ...validationProblem, status: 400.5 }],
    ["status as text", { ...validationProblem, status: "400" }],
    ["missing type", { ...validationProblem, type: undefined }],
    ["missing title", { ...validationProblem, title: 1 }],
    ["missing request_id", { ...validationProblem, request_id: undefined }],
    ["detail not text", { ...validationProblem, detail: { html: "<b>" } }],
  ])("rejects %s", (_label, body) => {
    expect(parseProblem(body)).toBeNull();
  });

  it("drops malformed field errors and keeps the valid ones", () => {
    const problem = parseProblem({
      ...validationProblem,
      errors: [{ field: "amount", code: "required", message: "x" }, { field: 1 }, "bad", null],
    });
    expect(problem?.errors).toEqual([{ field: "amount", code: "required", message: "x" }]);
  });

  it("ignores members outside the contract", () => {
    const problem = parseProblem({ ...validationProblem, stack: "at views.py:12" });
    expect(problem).not.toHaveProperty("stack");
  });

  it("accepts a problem without detail nor errors", () => {
    const minimal: Problem = { ...validationProblem };
    delete minimal.detail;
    delete minimal.errors;
    expect(parseProblem(minimal)).toEqual(minimal);
  });
});

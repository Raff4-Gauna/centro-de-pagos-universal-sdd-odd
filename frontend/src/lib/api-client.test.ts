import { describe, expect, it, vi } from "vitest";

import { API_BASE_URL, apiClient, createApiClient } from "./api-client";
import { ApiError, CLIENT_ERROR_CODES } from "./problem";

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
// This one does what the browser does, against jsdom's location.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

// The contract of 00 has no paths yet (`paths: {}`): the tests call the client untyped.
type UntypedGet = (
  path: string,
  init?: { baseUrl?: string; signal?: AbortSignal },
) => Promise<{ data?: unknown; response: Response }>;

function clientWith(fetchImpl: (request: Request) => Promise<Response>) {
  const fetchMock = vi.fn(fetchImpl);
  const client = createApiClient({ fetch: fetchMock, Request: BrowserRequest });
  return { get: client.GET as unknown as UntypedGet, fetchMock };
}

function json(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers: { "content-type": "application/json", ...init.headers },
  });
}

describe("typed API client (RF-PLT-15, ADR-0005, design.md §3.3.3)", () => {
  it("test_RF_PLT_15_api_client_uses_same_origin", async () => {
    const { get, fetchMock } = clientWith(async () => json({ status: "ok" }));

    const { data } = await get("/api/things/?page=2");

    expect(API_BASE_URL).toBe("");
    const request = fetchMock.mock.calls[0]![0];
    const target = new URL(request.url);
    expect(target.origin).toBe(window.location.origin);
    expect(`${target.pathname}${target.search}`).toBe("/api/things/?page=2");
    expect(data).toEqual({ status: "ok" });
  });

  it("test_RF_PLT_15_api_client_refuses_other_origins_and_non_api_paths", async () => {
    const { get, fetchMock } = clientWith(async () => json({}));

    await expect(get("/api/x/", { baseUrl: "https://backend.internal:8000" })).rejects.toThrow(
      "only same-origin /api/ requests are allowed",
    );
    await expect(get("/healthz")).rejects.toThrow("only same-origin /api/ requests are allowed");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("test_AC_PLT_23_api_client_throws_api_error_on_problem_json", async () => {
    const { get } = clientWith(async () =>
      json(
        {
          type: "urn:hub:problem:not_found",
          title: "No encontrado",
          status: 404,
          code: "not_found",
          request_id: "abc",
        },
        { status: 404, headers: { "content-type": "application/problem+json" } },
      ),
    );

    const failure = get("/api/missing/");

    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({
      status: 404,
      code: "not_found",
      requestId: "abc",
    });
  });

  it("test_AC_PLT_23_api_client_network_failure_is_api_error_without_cause", async () => {
    const { get } = clientWith(async () => {
      throw new TypeError("connect ECONNREFUSED 172.18.0.4:8000");
    });

    const error = await get("/api/x/").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: CLIENT_ERROR_CODES.network });
    expect(String((error as Error).message)).not.toContain("172.18");
  });

  it("test_RF_PLT_15_api_client_keeps_abort_errors", async () => {
    const abort = new DOMException("The operation was aborted.", "AbortError");
    const { get } = clientWith(async () => {
      throw abort;
    });

    await expect(get("/api/x/")).rejects.toBe(abort);
  });

  it("test_RF_PLT_15_api_client_success_is_not_wrapped", async () => {
    const { get } = clientWith(async () => new Response(null, { status: 204 }));

    const result = await get("/api/x/");

    expect(result.data).toBeUndefined();
    expect(result.response.status).toBe(204);
  });

  it("exports a ready client built the same way", () => {
    expect(typeof apiClient.GET).toBe("function");
  });
});

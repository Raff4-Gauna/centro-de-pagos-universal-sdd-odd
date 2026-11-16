import { describe, expect, it, vi } from "vitest";

import {
  API_BASE_URL,
  CSRF_COOKIE,
  apiClient,
  cookieValue,
  createApiClient,
  sessionExpiredUrl,
} from "./api-client";
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
type UntypedPost = (path: string, init?: { body?: unknown }) => Promise<{ response: Response }>;

type ClientExtras = {
  readCsrfToken?: () => string | null;
  onSessionExpired?: (url: string) => void;
};

function clientWith(fetchImpl: (request: Request) => Promise<Response>, extras: ClientExtras = {}) {
  const fetchMock = vi.fn(fetchImpl);
  const client = createApiClient({ fetch: fetchMock, Request: BrowserRequest, ...extras });
  return {
    get: client.GET as unknown as UntypedGet,
    post: client.POST as unknown as UntypedPost,
    del: client.DELETE as unknown as UntypedPost,
    fetchMock,
  };
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

  it("test_RN_IDA_13_api_client_echoes_the_csrf_cookie_on_mutations_only", async () => {
    const { get, post, del, fetchMock } = clientWith(async () => json({}), {
      readCsrfToken: () => "t".repeat(43),
    });

    await get("/api/me");
    await post("/api/auth/sessions/revoke-others/", { body: {} });
    await del("/api/things/1/");

    const sent = fetchMock.mock.calls.map(([request]) => request.headers.get("x-csrf-token"));
    expect(sent).toEqual([null, "t".repeat(43), "t".repeat(43)]);
    expect(CSRF_COOKIE).toBe("__Host-cpu_csrf");
  });

  it("test_RN_IDA_13_api_client_without_csrf_cookie_sends_no_header", async () => {
    const { post, fetchMock } = clientWith(async () => json({}), { readCsrfToken: () => null });

    await post("/api/x/", { body: {} });

    expect(fetchMock.mock.calls[0]![0].headers.has("x-csrf-token")).toBe(false);
  });

  it("test_RN_IDA_13_cookie_value_reads_one_cookie_and_refuses_ambiguity", () => {
    expect(cookieValue("a=1; __Host-cpu_csrf=abc; b=2", CSRF_COOKIE)).toBe("abc");
    expect(cookieValue("a=1", CSRF_COOKIE)).toBeNull();
    expect(cookieValue("", CSRF_COOKIE)).toBeNull();
    expect(cookieValue("__Host-cpu_csrf=", CSRF_COOKIE)).toBeNull();
    expect(cookieValue("__Host-cpu_csrf=a; __Host-cpu_csrf=b", CSRF_COOKIE)).toBeNull();
    expect(cookieValue("x__Host-cpu_csrf=a", CSRF_COOKIE)).toBeNull();
  });

  it("test_AC_IDA_26_api_client_401_goes_to_login_keeping_only_the_internal_path", async () => {
    window.history.pushState({}, "", "/cobros?page=2#detalle");
    const onSessionExpired = vi.fn();
    const { get } = clientWith(
      async () =>
        json(
          {
            type: "urn:hub:problem:session_revoked",
            title: "x",
            status: 401,
            code: "session_revoked",
            request_id: "r",
          },
          { status: 401, headers: { "content-type": "application/problem+json" } },
        ),
      { onSessionExpired },
    );

    // The query still fails: the screen does not show stale data while the browser navigates.
    await expect(get("/api/me")).rejects.toMatchObject({ status: 401, code: "session_revoked" });

    expect(onSessionExpired).toHaveBeenCalledExactlyOnceWith(
      "/login?error=session_expired&return_to=%2Fcobros%3Fpage%3D2",
    );
    window.history.pushState({}, "", "/");
  });

  it("test_AC_IDA_26_api_client_other_errors_and_the_login_page_do_not_redirect", async () => {
    const onSessionExpired = vi.fn();
    const { get } = clientWith(async () => json({}, { status: 403 }), { onSessionExpired });
    await expect(get("/api/x/")).rejects.toBeInstanceOf(ApiError);
    expect(onSessionExpired).not.toHaveBeenCalled();

    expect(sessionExpiredUrl({ pathname: "/login", search: "?error=x" })).toBeNull();
    expect(sessionExpiredUrl({ pathname: "/", search: "" })).toBe(
      "/login?error=session_expired&return_to=%2F",
    );
  });

  it("exports a ready client built the same way", () => {
    expect(typeof apiClient.GET).toBe("function");
  });
});

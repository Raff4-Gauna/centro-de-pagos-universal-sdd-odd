import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createApiClient,
  getActiveOrganizationId,
  ORGANIZATION_HEADER,
  orgQueryKey,
  setActiveOrganizationId,
  subscribeOrganizationErrors,
  type OrganizationErrorEvent,
} from "./api-client";
import { ApiError } from "./problem";

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

// No tenant-scoped path is in the contract yet (T-TEN-13): the tests call the client untyped.
type UntypedCall = (
  path: string,
  init?: { body?: unknown; headers?: Record<string, string> },
) => Promise<{ data?: unknown; response: Response }>;

const ORG_A = "6a1f0c2e-1b3d-4e5f-8a9b-0c1d2e3f4a5b";
const ORG_B = "7b2e1d3f-2c4e-4f60-9bac-1d2e3f4a5b6c";

function problem(status: number, code: string) {
  return new Response(
    JSON.stringify({ type: `urn:hub:problem:${code}`, title: "t", status, code, request_id: "r" }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

function clientWith(
  respond: () => Response,
  options: {
    readOrganizationId?: () => string | null;
    onOrganizationError?: (event: OrganizationErrorEvent) => void;
  } = {},
) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () => respond());
  const client = createApiClient({ fetch: fetchMock, Request: BrowserRequest, ...options });
  return {
    get: client.GET as unknown as UntypedCall,
    post: client.POST as unknown as UntypedCall,
    fetchMock,
  };
}

afterEach(() => setActiveOrganizationId(null));

describe("api-client and the active organization (RF-TEN-02, Q-119, design.md §3.9)", () => {
  it("test_RF_TEN_02_api_client_sends_the_tab_organization_on_every_request", async () => {
    const { get, post, fetchMock } = clientWith(() => new Response(null, { status: 204 }), {
      readOrganizationId: () => ORG_A,
    });

    await get("/api/branches/");
    await post("/api/branches/", { body: {} });

    const sent = fetchMock.mock.calls.map(([request]) => request.headers.get(ORGANIZATION_HEADER));
    expect(sent).toEqual([ORG_A, ORG_A]);
    expect(ORGANIZATION_HEADER).toBe("X-Organization-Id");
  });

  it("test_RF_TEN_02_api_client_keeps_the_organization_a_request_already_names", async () => {
    const { get, fetchMock } = clientWith(() => new Response(null, { status: 204 }), {
      readOrganizationId: () => ORG_B,
    });

    await get("/api/branches/", { headers: { [ORGANIZATION_HEADER]: ORG_A } });

    expect(fetchMock.mock.calls[0]![0].headers.get(ORGANIZATION_HEADER)).toBe(ORG_A);
  });

  it("test_RF_TEN_02_api_client_without_active_organization_sends_no_header", async () => {
    const { get, fetchMock } = clientWith(() => new Response(null, { status: 204 }));

    await get("/api/organizations/");

    expect(fetchMock.mock.calls[0]![0].headers.has(ORGANIZATION_HEADER)).toBe(false);
  });

  it("test_RF_TEN_02_api_client_reads_the_tab_organization_by_default", async () => {
    const { get, fetchMock } = clientWith(() => new Response(null, { status: 204 }));

    setActiveOrganizationId(ORG_B);
    await get("/api/branches/");

    expect(getActiveOrganizationId()).toBe(ORG_B);
    expect(fetchMock.mock.calls[0]![0].headers.get(ORGANIZATION_HEADER)).toBe(ORG_B);
  });

  it.each([
    [404, "organization_not_found"],
    [409, "organization_suspended"],
  ])("test_RF_TEN_02_api_client_reports_%i_%s_and_still_throws", async (status, code) => {
    const onOrganizationError = vi.fn();
    const { get } = clientWith(() => problem(status, code), {
      readOrganizationId: () => ORG_A,
      onOrganizationError,
    });

    await expect(get("/api/branches/")).rejects.toMatchObject({ status, code });

    expect(onOrganizationError).toHaveBeenCalledExactlyOnceWith({ code, organizationId: ORG_A });
  });

  it("test_RF_TEN_02_api_client_ignores_other_errors", async () => {
    const onOrganizationError = vi.fn();
    for (const response of [
      () => problem(404, "not_found"),
      () => problem(409, "conflict"),
      () => problem(403, "organization_not_found"),
      () => new Response("<html>", { status: 404, headers: { "content-type": "text/html" } }),
      () =>
        new Response("{not json", {
          status: 404,
          headers: { "content-type": "application/problem+json" },
        }),
    ]) {
      const { get } = clientWith(response, { onOrganizationError });
      await expect(get("/api/branches/")).rejects.toBeInstanceOf(ApiError);
    }
    expect(onOrganizationError).not.toHaveBeenCalled();
  });

  it("test_RF_TEN_02_api_client_notifies_subscribers_by_default", async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeOrganizationErrors(listener);
    const { get } = clientWith(() => problem(404, "organization_not_found"));

    setActiveOrganizationId(ORG_A);
    await expect(get("/api/branches/")).rejects.toBeInstanceOf(ApiError);
    unsubscribe();
    await expect(get("/api/branches/")).rejects.toBeInstanceOf(ApiError);

    expect(listener).toHaveBeenCalledExactlyOnceWith({
      code: "organization_not_found",
      organizationId: ORG_A,
    });
  });

  it("test_RF_TEN_02_org_query_keys_start_with_org_and_its_id", () => {
    expect(orgQueryKey(ORG_A, "branches", { active: true })).toEqual([
      "org",
      ORG_A,
      "branches",
      { active: true },
    ]);
  });
});

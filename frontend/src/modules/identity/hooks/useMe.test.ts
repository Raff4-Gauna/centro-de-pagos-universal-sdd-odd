import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api-client";
import { ApiError } from "@/lib/problem";

import { fetchMe, ME_QUERY_KEY } from "./useMe";

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

const ME = {
  id: "0b6f8a52-4a8e-4f61-9d0c-6d3b8f0e2a11",
  email: "ana@example.com",
  display_name: "Ana Pérez",
  avatar_url: null,
  memberships: [],
};

describe("useMe (RF-IDA-06, AC-IDA-30, design.md §6.2)", () => {
  it("test_RF_IDA_06_fetch_me_reads_api_me", async () => {
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(
      async () =>
        new Response(JSON.stringify(ME), { headers: { "content-type": "application/json" } }),
    );
    const client = createApiClient({ fetch: fetchMock, Request: BrowserRequest });
    await expect(fetchMe(client)).resolves.toEqual(ME);
    const request = fetchMock.mock.calls[0]![0];
    expect(request.method).toBe("GET");
    expect(new URL(request.url).pathname).toBe("/api/me/");
    expect(ME_QUERY_KEY).toEqual(["me"]);
  });

  it("test_RF_IDA_06_fetch_me_failure_is_an_api_error", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            type: "urn:hub:problem:internal_error",
            title: "Error interno",
            status: 500,
            code: "internal_error",
            request_id: "req-1",
          }),
          { status: 500, headers: { "content-type": "application/problem+json" } },
        ),
    );
    const client = createApiClient({ fetch: fetchMock, Request: BrowserRequest });
    const error = await fetchMe(client).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("internal_error");
  });
});

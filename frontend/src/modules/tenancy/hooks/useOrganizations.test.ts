import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api-client";
import { ApiError } from "@/lib/problem";

import {
  fetchOrganizations,
  ORGANIZATIONS_PAGE_SIZE,
  ORGANIZATIONS_QUERY_KEY,
  organizationsQueryOptions,
} from "./useOrganizations";

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

function organization(index: number) {
  return {
    id: `6a1f0c2e-1b3d-4e5f-8a9b-${String(index).padStart(12, "0")}`,
    name: `Empresa ${index}`,
    status: "active",
    role: "owner",
  };
}

function page(results: unknown[], count: number, next: string | null) {
  return new Response(JSON.stringify({ count, next, previous: null, results }), {
    headers: { "content-type": "application/json" },
  });
}

function clientWith(respond: (request: Request) => Response) {
  const fetchMock = vi.fn(async (request: Request) => respond(request));
  return { client: createApiClient({ fetch: fetchMock, Request: BrowserRequest }), fetchMock };
}

describe("useOrganizations (RF-TEN-02, T-TEN-12, design.md §6)", () => {
  it("test_RF_TEN_02_fetch_organizations_reads_every_page", async () => {
    const { client, fetchMock } = clientWith((request) =>
      new URL(request.url).searchParams.get("page") === "1"
        ? page([organization(1), organization(2)], 3, "/api/organizations/?page=2")
        : page([organization(3)], 3, null),
    );

    const list = await fetchOrganizations(client);

    expect(list.map(({ name }) => name)).toEqual(["Empresa 1", "Empresa 2", "Empresa 3"]);
    const urls = fetchMock.mock.calls.map(([request]) => new URL(request.url));
    expect(urls.map((url) => url.pathname)).toEqual(["/api/organizations/", "/api/organizations/"]);
    expect(urls.map((url) => url.searchParams.get("page"))).toEqual(["1", "2"]);
    expect(urls[0]!.searchParams.get("page_size")).toBe(String(ORGANIZATIONS_PAGE_SIZE));
  });

  it("test_RF_TEN_02_fetch_organizations_stops_at_count", async () => {
    const { client, fetchMock } = clientWith(() =>
      page([organization(1)], 1, "/api/organizations/?page=2"),
    );

    await expect(fetchOrganizations(client)).resolves.toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("test_RF_TEN_02_fetch_organizations_failure_is_an_api_error", async () => {
    const { client } = clientWith(() => new Response(null, { status: 204 }));

    const error = await fetchOrganizations(client).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(ORGANIZATIONS_QUERY_KEY).toEqual(["organizations"]);
    expect(organizationsQueryOptions(client).queryKey).toEqual(["organizations"]);
  });
});

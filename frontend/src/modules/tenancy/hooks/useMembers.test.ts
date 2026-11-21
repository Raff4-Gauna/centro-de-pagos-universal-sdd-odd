import { describe, expect, it, vi } from "vitest";

import { createApiClient, ORGANIZATION_HEADER } from "@/lib/api-client";
import { ApiError } from "@/lib/problem";

import { BrowserRequest } from "../components/branches.test-helpers";
import { ANA, ME } from "../components/members.test-helpers";
import { fetchMembers, MEMBERS_PAGE_SIZE, membersQueryKey, revokeMember } from "./useMembers";

const ORG_A = "6a1f0c2e-1b3d-4e5f-8a9b-0c1d2e3f4a5b";

function page(results: unknown[], count: number, next: string | null) {
  return new Response(JSON.stringify({ count, next, previous: null, results }), {
    headers: { "content-type": "application/json" },
  });
}

function clientWith(respond: (request: Request) => Response) {
  const fetchMock = vi.fn(async (request: Request) => respond(request));
  const client = createApiClient({
    fetch: fetchMock,
    Request: BrowserRequest,
    readCsrfToken: () => "csrf-test-token",
    onOrganizationError: () => undefined,
  });
  return { client, fetchMock };
}

describe("useMembers (RF-TEN-04, design.md §6)", () => {
  it("test_RF_TEN_04_fetch_reads_every_page_naming_the_company_and_status_of_the_key", async () => {
    const { client, fetchMock } = clientWith((request) =>
      new URL(request.url).searchParams.get("page") === "1"
        ? page([ME], 2, "/api/memberships/?page=2")
        : page([ANA], 2, null),
    );

    const list = await fetchMembers(client, membersQueryKey(ORG_A, "revoked"));

    expect(list.map(({ id }) => id)).toEqual([ME.id, ANA.id]);
    const requests = fetchMock.mock.calls.map(([request]) => request);
    expect(requests).toHaveLength(2);
    for (const request of requests) {
      const url = new URL(request.url);
      expect(url.pathname).toBe("/api/memberships/");
      expect(url.searchParams.get("status")).toBe("revoked");
      expect(url.searchParams.get("page_size")).toBe(String(MEMBERS_PAGE_SIZE));
      expect(request.headers.get(ORGANIZATION_HEADER)).toBe(ORG_A);
    }
  });

  it("test_RF_TEN_04_a_next_that_never_ends_is_bounded_by_count", async () => {
    const { client, fetchMock } = clientWith(() => page([ME], 1, "/api/memberships/?page=2"));

    await fetchMembers(client, membersQueryKey(ORG_A, "active"));

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("test_RF_TEN_04_revoke_needs_a_204", async () => {
    const { client } = clientWith(
      () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }),
    );

    await expect(revokeMember(client, ORG_A, ANA.id)).rejects.toBeInstanceOf(ApiError);
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { createApiClient, ORGANIZATION_HEADER } from "@/lib/api-client";
import { ApiError } from "@/lib/problem";

import { BrowserRequest, CENTRO, NORTE, problem } from "../components/branches.test-helpers";
import {
  BRANCHES_PAGE_SIZE,
  branchesQueryKey,
  changeBranchState,
  fetchBranches,
  useCreateBranch,
} from "./useBranches";
import { currentOrganizationQueryKey } from "./useCurrentOrganizationDetails";

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

describe("useBranches (RF-TEN-06, design.md §3.9, §6)", () => {
  it("test_RF_TEN_06_fetch_reads_every_page_naming_the_company_of_the_key", async () => {
    const { client, fetchMock } = clientWith((request) =>
      new URL(request.url).searchParams.get("page") === "1"
        ? page([CENTRO], 2, "/api/branches/?page=2")
        : page([NORTE], 2, null),
    );

    const list = await fetchBranches(client, branchesQueryKey(ORG_A, "all"));

    expect(list.map(({ name }) => name)).toEqual(["Centro", "Norte"]);
    const requests = fetchMock.mock.calls.map(([request]) => request);
    expect(requests).toHaveLength(2);
    for (const request of requests) {
      const url = new URL(request.url);
      expect(url.pathname).toBe("/api/branches/");
      expect(url.searchParams.get("page_size")).toBe(String(BRANCHES_PAGE_SIZE));
      expect(url.searchParams.has("is_active")).toBe(false);
      expect(request.headers.get(ORGANIZATION_HEADER)).toBe(ORG_A);
    }
  });

  it("test_RF_TEN_06_filter_maps_to_is_active", async () => {
    const { client, fetchMock } = clientWith(() => page([], 0, null));

    await fetchBranches(client, branchesQueryKey(ORG_A, "active"));
    await fetchBranches(client, branchesQueryKey(ORG_A, "inactive"));

    const values = fetchMock.mock.calls.map(([request]) =>
      new URL(request.url).searchParams.get("is_active"),
    );
    expect(values).toEqual(["true", "false"]);
  });

  it("test_RF_TEN_06_a_next_that_never_ends_stops_at_count", async () => {
    const { client, fetchMock } = clientWith(() => page([CENTRO], 1, "/api/branches/?page=9"));

    await fetchBranches(client, branchesQueryKey(ORG_A, "all"));

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("test_RF_TEN_06_transition_posts_to_its_route", async () => {
    const { client, fetchMock } = clientWith(
      () =>
        new Response(JSON.stringify(NORTE), { headers: { "content-type": "application/json" } }),
    );

    await changeBranchState(client, ORG_A, NORTE.id, "reactivate");

    const [request] = fetchMock.mock.calls[0]!;
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe(`/api/branches/${NORTE.id}/reactivate/`);
    expect(request.headers.get(ORGANIZATION_HEADER)).toBe(ORG_A);
  });

  it("test_AC_TEN_28_suspended_write_rereads_branches_and_allowed_actions", async () => {
    const { client } = clientWith(() =>
      problem(409, "organization_suspended", "Organización suspendida"),
    );
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCreateBranch(ORG_A, client), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ name: "Sur" }).catch(() => undefined);
    });

    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toContainEqual(["org", ORG_A, "branches"]);
    expect(keys).toContainEqual(currentOrganizationQueryKey(ORG_A));
  });
});

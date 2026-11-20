import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname, useRouter } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createApiClient,
  ORGANIZATION_HEADER,
  orgHeaderFromKey,
  orgQueryKey,
} from "@/lib/api-client";

import {
  clearTabOrganization,
  type MyOrganization,
  readTabOrganization,
} from "../lib/active-organization";
import { ActiveOrgProvider, useActiveOrganization } from "./ActiveOrgProvider";

// Review of #122: the company a request names must be the one its query is cached under, also in
// the commit where the company is resolved or changes (the children's effects, where TanStack
// Query starts fetching, run before the provider's) and when `sessionStorage` refuses to write.

const listOrganizations = vi.hoisted(() => vi.fn<() => Promise<MyOrganization[]>>());

vi.mock("next/navigation", () => ({ usePathname: vi.fn(), useRouter: vi.fn() }));
vi.mock("../hooks/useOrganizations", async () => {
  const { queryOptions, useQuery: query } = await import("@tanstack/react-query");
  const organizationsQueryOptions = () =>
    queryOptions({ queryKey: ["organizations"], queryFn: () => listOrganizations() });
  return { organizationsQueryOptions, useOrganizations: () => query(organizationsQueryOptions()) };
});
vi.mock("../lib/active-organization", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/active-organization")>()),
  saveDefaultOrganization: vi.fn(async () => undefined),
}));

const ACME: MyOrganization = {
  id: "6a1f0c2e-1b3d-4e5f-8a9b-0c1d2e3f4a5b",
  name: "Acme",
  status: "active",
  role: "owner",
};
const BETA: MyOrganization = {
  id: "7b2e1d3f-2c4e-4f60-9bac-1d2e3f4a5b6c",
  name: "Beta",
  status: "active",
  role: "viewer",
};
const NAMES = new Map([ACME, BETA].map(({ id, name }) => [id, name]));

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

// The backend answers with the company the request names: what gets cached shows which one it was.
const sentHeaders: (string | null)[] = [];
const client = createApiClient({
  Request: BrowserRequest,
  fetch: async (request: Request) => {
    const organizationId = request.headers.get(ORGANIZATION_HEADER);
    sentHeaders.push(organizationId);
    const name = organizationId === null ? undefined : NAMES.get(organizationId);
    return new Response(JSON.stringify({ id: organizationId, name }), {
      headers: { "content-type": "application/json" },
    });
  },
});

// A screen of tenant-scoped data, mounted in the same commit in which the company resolves.
function CompanyData() {
  const { organizationId } = useActiveOrganization();
  const query = useQuery({
    queryKey: orgQueryKey(organizationId ?? "", "current"),
    enabled: organizationId !== null,
    queryFn: async ({ queryKey, signal }) => {
      const { data } = await client.GET("/api/organizations/current/", {
        params: { header: orgHeaderFromKey(queryKey) },
        signal,
      });
      return data;
    },
  });
  return (
    <div>
      <p data-testid="shown">{organizationId === null ? "-" : NAMES.get(organizationId)}</p>
      <p data-testid="data">{query.data?.name ?? "-"}</p>
    </div>
  );
}

function SelectBeta() {
  const { selectOrganization } = useActiveOrganization();
  return (
    <button type="button" onClick={() => selectOrganization(BETA.id)}>
      Beta
    </button>
  );
}

let queryClient: QueryClient;

function renderShell(defaultOrganizationId: string | null) {
  return render(
    <QueryClientProvider client={queryClient}>
      <ActiveOrgProvider defaultOrganizationId={defaultOrganizationId}>
        <SelectBeta />
        <CompanyData />
      </ActiveOrgProvider>
    </QueryClientProvider>,
  );
}

const cached = (organizationId: string) =>
  queryClient.getQueryData<{ name?: string }>(orgQueryKey(organizationId, "current"))?.name;

beforeEach(() => {
  clearTabOrganization();
  sentHeaders.length = 0;
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(usePathname).mockReturnValue("/inicio");
  vi.mocked(useRouter).mockReturnValue({ replace: vi.fn() } as unknown as ReturnType<
    typeof useRouter
  >);
  listOrganizations.mockResolvedValue([ACME, BETA]);
});

afterEach(() => {
  clearTabOrganization();
  window.sessionStorage.clear();
  queryClient.clear();
});

describe("ActiveOrgProvider and the requests of its children (RF-TEN-02, Q-119 b, ADR-0004 §7)", () => {
  it("test_RF_TEN_02_initial_load_first_request_names_the_resolved_company", async () => {
    renderShell(BETA.id);

    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("Beta"));
    expect(screen.getByTestId("shown")).toHaveTextContent("Beta");
    // No request left without the header, nor with another company.
    expect(sentHeaders).toEqual([BETA.id]);
  });

  it("test_RF_TEN_02_change_in_the_same_commit_names_the_company_of_the_key", async () => {
    renderShell(ACME.id);
    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("Acme"));

    await userEvent.click(screen.getByRole("button", { name: "Beta" }));

    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("Beta"));
    expect(screen.getByTestId("shown")).toHaveTextContent("Beta");
    expect(sentHeaders).toEqual([ACME.id, BETA.id]);
    expect(cached(BETA.id)).toBe("Beta");
    expect(cached(ACME.id)).toBeUndefined();
  });

  it("test_RF_TEN_02_change_with_session_storage_failing_keeps_key_and_header_together", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    renderShell(ACME.id);
    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("Acme"));

    await userEvent.click(screen.getByRole("button", { name: "Beta" }));

    // The tab keeps the choice in memory: it shows Beta, asks for Beta, caches Beta under Beta.
    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("Beta"));
    expect(screen.getByTestId("shown")).toHaveTextContent("Beta");
    expect(readTabOrganization()).toBe(BETA.id);
    expect(sentHeaders).toEqual([ACME.id, BETA.id]);
    expect(cached(BETA.id)).toBe("Beta");
    expect(cached(ACME.id)).toBeUndefined();
  });
});

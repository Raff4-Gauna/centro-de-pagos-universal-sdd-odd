import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { usePathname, useRouter } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient, organizationHeader } from "@/lib/api-client";

import { useCurrentOrganization } from "../hooks/useCurrentOrganization";
import {
  clearTabOrganization,
  type MyOrganization,
  saveDefaultOrganization,
  TAB_ORGANIZATION_KEY,
} from "../lib/active-organization";
import {
  ActiveOrgProvider,
  HOME_PATH,
  LOST_ACCESS_TEXT,
  NO_ORGANIZATION_PATH,
  useActiveOrganization,
} from "./ActiveOrgProvider";

const listOrganizations = vi.hoisted(() => vi.fn<() => Promise<MyOrganization[]>>());

vi.mock("next/navigation", () => ({ usePathname: vi.fn(), useRouter: vi.fn() }));
vi.mock("../hooks/useOrganizations", async () => {
  const { queryOptions, useQuery } = await import("@tanstack/react-query");
  const organizationsQueryOptions = () =>
    queryOptions({ queryKey: ["organizations"], queryFn: () => listOrganizations() });
  return {
    organizationsQueryOptions,
    useOrganizations: () => useQuery(organizationsQueryOptions()),
  };
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
// A company the person no longer belongs to.
const LEFT_ORGANIZATION_ID = "8c3f2e4a-3d5f-4a71-8cbd-2e3f4a5b6c7d";

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

// A tenant-scoped request about `organizationId` answered with `code`: the api-client tells the
// provider (by default).
async function answerWith(status: number, code: string, organizationId: string = ACME.id) {
  const client = createApiClient({
    Request: BrowserRequest,
    fetch: async () =>
      new Response(
        JSON.stringify({
          type: `urn:hub:problem:${code}`,
          title: "t",
          status,
          code,
          request_id: "r",
        }),
        { status, headers: { "content-type": "application/problem+json" } },
      ),
  });
  const get = client.GET as unknown as (
    path: string,
    init: { headers: Record<string, string> },
  ) => Promise<unknown>;
  await act(async () => {
    await get("/api/branches/", { headers: organizationHeader(organizationId) }).catch(
      () => undefined,
    );
  });
}

function Probe() {
  const { organizationId, selectOrganization } = useActiveOrganization();
  const { organization, isSuspended } = useCurrentOrganization();
  return (
    <div>
      <p data-testid="active">{organizationId ?? "none"}</p>
      <p data-testid="current">{organization ? `${organization.name}:${isSuspended}` : "-"}</p>
      <button type="button" onClick={() => selectOrganization(BETA.id)}>
        Beta
      </button>
    </div>
  );
}

let queryClient: QueryClient;
const replace = vi.fn();

function renderProvider(defaultOrganizationId: string | null = null) {
  return render(
    <QueryClientProvider client={queryClient}>
      <ActiveOrgProvider defaultOrganizationId={defaultOrganizationId}>
        <Probe />
      </ActiveOrgProvider>
    </QueryClientProvider>,
  );
}

const active = () => screen.getByTestId("active");

beforeEach(() => {
  clearTabOrganization();
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(usePathname).mockReturnValue("/inicio");
  vi.mocked(useRouter).mockReturnValue({ replace } as unknown as ReturnType<typeof useRouter>);
  listOrganizations.mockResolvedValue([ACME, BETA]);
});

afterEach(() => {
  clearTabOrganization();
  window.sessionStorage.clear();
  queryClient.clear();
});

describe("ActiveOrgProvider (RF-TEN-02, spec §14, Q-119, Q-205, design.md §3.9)", () => {
  it("test_RF_TEN_02_tab_value_wins_over_the_bff_default", async () => {
    window.sessionStorage.setItem(TAB_ORGANIZATION_KEY, BETA.id);
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(BETA.id));
    expect(saveDefaultOrganization).not.toHaveBeenCalled();
  });

  it("test_RF_TEN_02_bff_default_when_the_tab_has_none", async () => {
    renderProvider(BETA.id);
    await waitFor(() => expect(active()).toHaveTextContent(BETA.id));
    // The tab keeps it as its own value from now on.
    expect(window.sessionStorage.getItem(TAB_ORGANIZATION_KEY)).toBe(BETA.id);
    expect(screen.getByTestId("current")).toHaveTextContent("Beta:false");
  });

  it("test_RF_TEN_02_first_by_name_without_tab_value_or_default", async () => {
    window.sessionStorage.setItem(TAB_ORGANIZATION_KEY, LEFT_ORGANIZATION_ID);
    renderProvider(null);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));
    expect(saveDefaultOrganization).not.toHaveBeenCalled();
  });

  it("test_RF_TEN_02_change_clears_org_cache_and_saves_default", async () => {
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));
    queryClient.setQueryData(["org", ACME.id, "branches"], ["sucursal"]);

    await userEvent.click(screen.getByRole("button", { name: "Beta" }));

    await waitFor(() => expect(active()).toHaveTextContent(BETA.id));
    expect(queryClient.getQueryData(["org", ACME.id, "branches"])).toBeUndefined();
    expect(queryClient.getQueryData(["organizations"])).toEqual([ACME, BETA]);
    expect(window.sessionStorage.getItem(TAB_ORGANIZATION_KEY)).toBe(BETA.id);
    expect(saveDefaultOrganization).toHaveBeenCalledExactlyOnceWith(BETA.id);
  });

  // Not picked in the selector: the list was reread (here, invalidated) without the company.
  it("test_RF_TEN_02_list_without_the_active_company_clears_its_cache_and_saves_default", async () => {
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));
    queryClient.setQueryData(["org", ACME.id, "branches"], ["sucursal"]);
    listOrganizations.mockResolvedValue([BETA]);

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["organizations"] });
    });

    await waitFor(() => expect(active()).toHaveTextContent(BETA.id));
    expect(queryClient.getQueryData(["org", ACME.id, "branches"])).toBeUndefined();
    expect(saveDefaultOrganization).toHaveBeenCalledExactlyOnceWith(BETA.id);
  });

  it("test_RF_TEN_02_organization_not_found_moves_to_the_next_and_says_so", async () => {
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));
    listOrganizations.mockResolvedValue([BETA]);

    await answerWith(404, "organization_not_found");

    await waitFor(() => expect(active()).toHaveTextContent(BETA.id));
    expect(await screen.findByText(LOST_ACCESS_TEXT)).toBeInTheDocument();
    expect(saveDefaultOrganization).toHaveBeenCalledExactlyOnceWith(BETA.id);
    expect(replace).not.toHaveBeenCalled();
  });

  it("test_RF_TEN_02_organization_not_found_with_none_left_goes_to_no_organization", async () => {
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));
    listOrganizations.mockResolvedValue([]);

    await answerWith(404, "organization_not_found");

    await waitFor(() => expect(replace).toHaveBeenCalledWith(NO_ORGANIZATION_PATH));
    expect(active()).toHaveTextContent("none");
    expect(saveDefaultOrganization).toHaveBeenCalledExactlyOnceWith(null);
  });

  it("test_RF_TEN_02_organization_not_found_while_still_a_member_keeps_it", async () => {
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));

    await answerWith(404, "organization_not_found");

    await waitFor(() => expect(listOrganizations).toHaveBeenCalledTimes(2));
    expect(active()).toHaveTextContent(ACME.id);
    expect(screen.queryByText(LOST_ACCESS_TEXT)).not.toBeInTheDocument();
  });

  it("test_RF_TEN_02_answers_about_another_organization_are_ignored", async () => {
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));
    await userEvent.click(screen.getByRole("button", { name: "Beta" }));
    await waitFor(() => expect(active()).toHaveTextContent(BETA.id));

    // A late answer for Acme: the request was sent before the change.
    await answerWith(404, "organization_not_found", ACME.id);

    expect(listOrganizations).toHaveBeenCalledTimes(1);
    expect(active()).toHaveTextContent(BETA.id);
  });

  it("test_RF_TEN_02_organization_suspended_rereads_the_status", async () => {
    renderProvider(ACME.id);
    await waitFor(() => expect(active()).toHaveTextContent(ACME.id));
    listOrganizations.mockResolvedValue([{ ...ACME, status: "suspended" }, BETA]);

    await answerWith(409, "organization_suspended");

    await waitFor(() => expect(screen.getByTestId("current")).toHaveTextContent("Acme:true"));
    expect(active()).toHaveTextContent(ACME.id);
  });

  it("test_RF_TEN_02_no_memberships_goes_to_no_organization_once", async () => {
    listOrganizations.mockResolvedValue([]);
    const { unmount } = renderProvider(ACME.id);
    await waitFor(() => expect(replace).toHaveBeenCalledExactlyOnceWith(NO_ORGANIZATION_PATH));
    unmount();

    replace.mockClear();
    vi.mocked(usePathname).mockReturnValue(NO_ORGANIZATION_PATH);
    renderProvider(null);
    await waitFor(() => expect(active()).toHaveTextContent("none"));
    expect(replace).not.toHaveBeenCalled();
  });

  it("test_AC_TEN_39_a_company_on_no_organization_goes_to_home", async () => {
    // An invitation accepted from "sin organización" brings the first company to the list.
    vi.mocked(usePathname).mockReturnValue(NO_ORGANIZATION_PATH);
    listOrganizations.mockResolvedValue([]);
    renderProvider(null);
    await waitFor(() => expect(active()).toHaveTextContent("none"));
    expect(replace).not.toHaveBeenCalled();

    listOrganizations.mockResolvedValue([BETA]);
    await act(() => queryClient.invalidateQueries({ queryKey: ["organizations"] }));

    await waitFor(() => expect(replace).toHaveBeenCalledExactlyOnceWith(HOME_PATH));
    expect(active()).toHaveTextContent(BETA.id);
  });

  it("test_RF_TEN_02_hook_outside_the_provider_fails", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Probe />)).toThrow("inside ActiveOrgProvider");
  });
});

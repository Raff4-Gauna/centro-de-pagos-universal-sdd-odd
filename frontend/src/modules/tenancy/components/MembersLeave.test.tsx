import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MembersPage from "@/app/(dashboard)/configuracion/colaboradores/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { ActiveOrgProvider } from "../context/ActiveOrgProvider";
import { clearTabOrganization, readTabOrganization } from "../lib/active-organization";
import { json, problem } from "./branches.test-helpers";
import { MEMBER_EXIT_TEXTS } from "./MemberExitDialog";
import { ANA, ME, memberPage } from "./members.test-helpers";
import { MEMBERS_TEXTS } from "./MembersTable";
import { ACME, BETA } from "./tenancy.test-helpers";

// Leaving from "Colaboradores" with the real shell (ActiveOrgProvider, design.md §3.9): once the
// backend answered `204`, the tab drops the company it left, moves to the next one, and no request
// names the company left again.
type Respond = (request: Request) => Response | Promise<Response>;
const network = vi.hoisted(() => ({
  respond: (() => new Response(null, { status: 500 })) as Respond,
  requests: [] as Request[],
}));
const router = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/configuracion/colaboradores",
  useRouter: () => router,
}));
vi.mock("../lib/active-organization", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/active-organization")>()),
  saveDefaultOrganization: vi.fn(async () => undefined),
}));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const { BrowserRequest } = await import("./branches.test-helpers");
  return {
    ...actual,
    apiClient: actual.createApiClient({
      Request: BrowserRequest,
      readCsrfToken: () => "csrf-test-token",
      onSessionExpired: () => undefined,
      onOrganizationError: () => undefined,
      fetch: async (request: Request) => {
        network.requests.push(request.clone());
        return network.respond(request);
      },
    }),
  };
});

beforeEach(() => {
  clearTabOrganization();
});

afterEach(() => {
  network.requests.length = 0;
  router.replace.mockReset();
});

describe("Abandonar desde Colaboradores (RF-TEN-04, AC-TEN-31, design.md §3.9)", () => {
  it("test_AC_TEN_31_leaving_moves_the_tab_to_the_next_company", async () => {
    let left = false;
    network.respond = (request) => {
      const { pathname } = new URL(request.url);
      const company = request.headers.get(ORGANIZATION_HEADER);
      if (pathname === "/api/organizations/") {
        const list = left ? [BETA] : [ACME, BETA];
        return json({ count: list.length, next: null, previous: null, results: list });
      }
      if (pathname === "/api/memberships/me/leave/") {
        left = true;
        return new Response(null, { status: 204 });
      }
      if (pathname === "/api/memberships/") {
        if (left && company === ACME.id) {
          return problem(404, "organization_not_found", "Organización no encontrada");
        }
        return memberPage(company === ACME.id ? [ME] : [ANA]);
      }
      return problem(404, "not_found", "No encontrado");
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ActiveOrgProvider defaultOrganizationId={ACME.id}>
          <MembersPage />
        </ActiveOrgProvider>
      </QueryClientProvider>,
    );

    const me = (await screen.findByRole("cell", { name: "yo@acme.test" })).closest("tr")!;
    await userEvent.click(within(me).getByRole("button", { name: MEMBERS_TEXTS.leave }));
    const sent = network.requests.length;
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: MEMBER_EXIT_TEXTS.leave.confirm,
      }),
    );

    // The tab now shows the next company, with its own members, and the dialog is gone.
    expect(await screen.findByRole("cell", { name: "ana@acme.test" })).toBeVisible();
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(readTabOrganization()).toBe(BETA.id));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/inicio"));
    // After the leave itself, no request names the company left.
    const after = network.requests.slice(sent + 1);
    expect(after.every((request) => request.headers.get(ORGANIZATION_HEADER) !== ACME.id)).toBe(
      true,
    );
    // Its cached data is gone too.
    expect(queryClient.getQueriesData({ queryKey: ["org", ACME.id] })).toHaveLength(0);
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CompanyPage from "@/app/(dashboard)/configuracion/empresa/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { ActiveOrgProvider } from "../context/ActiveOrgProvider";
import { clearTabOrganization, readTabOrganization } from "../lib/active-organization";
import { LAST_OWNER_TEXT } from "../lib/member-errors";
import { currentOrganization, json, problem } from "./branches.test-helpers";
import { COMPANY_TEXTS } from "./CompanyScreen";
import { MEMBER_EXIT_TEXTS } from "./MemberExitDialog";
import { ACME, BETA } from "./tenancy.test-helpers";

// "Abandonar la empresa" from "Datos de la empresa" with the real shell (ActiveOrgProvider,
// RF-TEN-04, design.md §3.9): after the `204` the tab drops the company and goes to "Inicio", or
// to "sin organización" when none is left; `409 last_owner` stays in the dialog, explained.
type Respond = (request: Request) => Response | Promise<Response>;
const network = vi.hoisted(() => ({
  respond: (() => new Response(null, { status: 500 })) as Respond,
  requests: [] as Request[],
}));
const router = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/configuracion/empresa",
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

// `leave` answers the leave; afterwards the person keeps only `after`.
function backend(after: (typeof ACME)[], leave: () => Response): Respond {
  let left = false;
  return (request) => {
    const { pathname } = new URL(request.url);
    const company = request.headers.get(ORGANIZATION_HEADER);
    if (pathname === "/api/organizations/") {
      const list = left ? after : [ACME, BETA];
      return json({ count: list.length, next: null, previous: null, results: list });
    }
    if (pathname === "/api/memberships/me/leave/") {
      const answer = leave();
      left = answer.status === 204;
      return answer;
    }
    if (pathname === "/api/organizations/current/") {
      if (left && company === ACME.id) {
        return problem(404, "organization_not_found", "Organización no encontrada");
      }
      const details = currentOrganization(["org.read", "member.leave"]);
      return json(company === ACME.id ? details : { ...details, id: BETA.id, name: "Beta" });
    }
    return problem(404, "not_found", "No encontrado");
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ActiveOrgProvider defaultOrganizationId={ACME.id}>
        <CompanyPage />
      </ActiveOrgProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

async function confirmLeave() {
  await userEvent.click(await screen.findByRole("button", { name: COMPANY_TEXTS.leave }));
  const dialog = screen.getByRole("dialog", { name: MEMBER_EXIT_TEXTS.leave.title() });
  await userEvent.click(
    within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.leave.confirm }),
  );
  return dialog;
}

beforeEach(() => {
  clearTabOrganization();
});

afterEach(() => {
  network.requests.length = 0;
  router.replace.mockReset();
});

describe("Abandonar desde Datos de la empresa (RF-TEN-04, design.md §3.9)", () => {
  it("test_RF_TEN_04_leaving_moves_the_tab_and_goes_home", async () => {
    network.respond = backend([BETA], () => new Response(null, { status: 204 }));
    const queryClient = renderPage();
    expect(await screen.findByText("Acme")).toBeVisible();
    await confirmLeave();

    const leave = network.requests.find(({ url }) => url.endsWith("/api/memberships/me/leave/"));
    expect(leave?.method).toBe("POST");
    expect(leave?.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    expect(await screen.findByText("Beta")).toBeVisible();
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(readTabOrganization()).toBe(BETA.id));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/inicio"));
    expect(queryClient.getQueriesData({ queryKey: ["org", ACME.id] })).toHaveLength(0);
  });

  it("test_RF_TEN_04_leaving_the_last_company_goes_to_sin_organizacion", async () => {
    network.respond = backend([], () => new Response(null, { status: 204 }));
    renderPage();
    await confirmLeave();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/sin-organizacion"));
    expect(router.replace).not.toHaveBeenCalledWith("/inicio");
  });

  it("test_RF_TEN_04_last_owner_is_explained_and_nothing_moves", async () => {
    network.respond = backend([BETA], () =>
      problem(409, "last_owner", "Último dueño", { detail: "owner" }),
    );
    renderPage();
    const dialog = await confirmLeave();

    expect(await within(dialog).findByText(LAST_OWNER_TEXT)).toBeVisible();
    expect(within(dialog).queryByText("owner")).toBeNull();
    expect(screen.getByRole("dialog", { name: MEMBER_EXIT_TEXTS.leave.title() })).toBeVisible();
    expect(router.replace).not.toHaveBeenCalled();
    expect(readTabOrganization()).toBe(ACME.id);

    await userEvent.click(within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.cancel }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

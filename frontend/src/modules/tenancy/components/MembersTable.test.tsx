import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MembersPage from "@/app/(dashboard)/configuracion/colaboradores/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { Member } from "../hooks/useMembers";
import { ROLE_LABELS } from "../lib/role-labels";
import { problem } from "./branches.test-helpers";
import { MEMBER_ROLE_TEXTS } from "./MemberRoleDialog";
import { ANA, EX, ME, membersAnswer, OTRO } from "./members.test-helpers";
import { MEMBERS_TEXTS } from "./MembersTable";
import { ACME, activeOrganizationResult, BETA } from "./tenancy.test-helpers";

// Configuración → Colaboradores, members (RF-TEN-04, spec §14, design.md §3.9): the screen talks
// to a fake BFF through the real api-client, so what is checked is what goes on the wire (path,
// company header, `?status=`) and what the screen shows from the backend's answers: each row's
// actions come only from its `allowed_actions` and `assignable_roles`, never from a role.
type Respond = (request: Request) => Response | Promise<Response>;
const network = vi.hoisted(() => ({
  respond: (() => new Response(null, { status: 500 })) as Respond,
  requests: [] as Request[],
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("../context/ActiveOrgProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../context/ActiveOrgProvider")>()),
  useActiveOrganization: vi.fn(),
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

function backend(members: readonly Member[]): Respond {
  return (request) =>
    new URL(request.url).pathname === "/api/memberships/"
      ? membersAnswer(request, members)
      : problem(404, "not_found", "No encontrado");
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page = () => (
    <QueryClientProvider client={queryClient}>
      <MembersPage />
    </QueryClientProvider>
  );
  const view = render(page());
  return { rerender: () => view.rerender(page()) };
}

async function rowOf(email: string): Promise<HTMLElement> {
  const cell = await screen.findByRole("cell", { name: email });
  return cell.closest("tr")!;
}

function listRequests(): Request[] {
  return network.requests.filter(
    (request) => new URL(request.url).pathname === "/api/memberships/",
  );
}

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
  network.respond = () => new Response(null, { status: 500 });
});

describe("Colaboradores: miembros (RF-TEN-04, spec §14, design.md §3.9)", () => {
  it("test_RF_TEN_04_lists_members_with_role_labels_and_the_company_header", async () => {
    network.respond = backend([ME, ANA, OTRO]);
    renderPage();

    expect(screen.getByRole("heading", { level: 1, name: MEMBERS_TEXTS.title })).toBeVisible();
    const ana = await rowOf("ana@acme.test");
    expect(ana).toHaveTextContent("Ana Pérez");
    expect(within(ana).getByText(ROLE_LABELS.operator)).toBeVisible();
    expect(within(await rowOf("yo@acme.test")).getByText(ROLE_LABELS.owner)).toBeVisible();
    // Q-232: the role code is never shown.
    expect(screen.queryByText("operator")).toBeNull();
    expect(screen.queryByText("owner")).toBeNull();
    // A person without a display name shows the placeholder, never a blank cell.
    expect(within(await rowOf("otro@acme.test")).getByText(MEMBERS_TEXTS.missing)).toBeVisible();

    const [list] = listRequests();
    expect(list!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    expect(new URL(list!.url).searchParams.get("status")).toBe("active");
  });

  it("test_RF_TEN_04_row_actions_follow_allowed_actions_and_assignable_roles", async () => {
    network.respond = backend([ME, ANA, OTRO, { ...ANA, id: "x", assignable_roles: [] }]);
    renderPage();

    const me = await rowOf("yo@acme.test");
    expect(within(me).getByRole("button", { name: MEMBERS_TEXTS.changeRole })).toBeVisible();
    expect(within(me).getByRole("button", { name: MEMBERS_TEXTS.leave })).toBeVisible();
    expect(within(me).queryByRole("button", { name: MEMBERS_TEXTS.revoke })).toBeNull();

    const rows = screen
      .getAllByRole("cell", { name: "ana@acme.test" })
      .map((c) => c.closest("tr")!);
    expect(within(rows[0]!).getByRole("button", { name: MEMBERS_TEXTS.revoke })).toBeVisible();
    expect(within(rows[0]!).getByRole("button", { name: MEMBERS_TEXTS.changeRole })).toBeVisible();
    expect(within(rows[0]!).queryByRole("button", { name: MEMBERS_TEXTS.leave })).toBeNull();
    // `member.change_role` without a role to assign offers nothing to pick.
    expect(within(rows[1]!).queryByRole("button", { name: MEMBERS_TEXTS.changeRole })).toBeNull();

    expect(within(await rowOf("otro@acme.test")).queryByRole("button")).toBeNull();
  });

  it("test_RF_TEN_04_role_dialog_offers_only_assignable_roles", async () => {
    network.respond = backend([ANA]);
    renderPage();

    const ana = await rowOf("ana@acme.test");
    await userEvent.click(within(ana).getByRole("button", { name: MEMBERS_TEXTS.changeRole }));
    const dialog = screen.getByRole("dialog", { name: MEMBER_ROLE_TEXTS.title("Ana Pérez") });
    await userEvent.click(
      within(dialog).getByRole("combobox", { name: MEMBER_ROLE_TEXTS.newRole }),
    );
    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual([ROLE_LABELS.admin, ROLE_LABELS.viewer]);
  });

  it("test_RF_TEN_04_without_any_action_there_is_no_actions_column", async () => {
    network.respond = backend([OTRO]);
    renderPage();

    await rowOf("otro@acme.test");
    expect(screen.queryByRole("button", { name: MEMBERS_TEXTS.changeRole })).toBeNull();
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
  });

  it("test_RF_TEN_04_filter_reads_ended_members_with_their_reason", async () => {
    network.respond = backend([ME, EX]);
    renderPage();
    await rowOf("yo@acme.test");

    await userEvent.click(screen.getByRole("button", { name: MEMBERS_TEXTS.filters.revoked }));
    const ex = await rowOf("ex@acme.test");
    expect(within(ex).getByText(MEMBERS_TEXTS.endedReasons.left)).toBeVisible();
    expect(within(ex).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("cell", { name: "yo@acme.test" })).toBeNull();

    const statuses = listRequests().map((r) => new URL(r.url).searchParams.get("status"));
    expect(statuses).toEqual(["active", "revoked"]);
  });

  it("test_RF_TEN_04_empty_state_per_filter", async () => {
    network.respond = backend([ME]);
    renderPage();
    await rowOf("yo@acme.test");

    await userEvent.click(screen.getByRole("button", { name: MEMBERS_TEXTS.filters.revoked }));
    expect(await screen.findByRole("region", { name: MEMBERS_TEXTS.emptyRevoked })).toBeVisible();
    // A table is never shown empty.
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("test_AC_TEN_34_forbidden_shows_no_permission", async () => {
    network.respond = () => problem(403, "forbidden", "Acción no permitida");
    renderPage();

    expect(await screen.findByRole("region", { name: MEMBERS_TEXTS.forbidden })).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reintentar" })).toBeNull();
  });

  it("test_RF_TEN_04_error_retries_the_same_request", async () => {
    network.respond = () => problem(500, "internal_error", "Error interno");
    renderPage();

    expect(await screen.findByText("Error interno")).toBeVisible();
    network.respond = backend([ANA]);
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("cell", { name: "ana@acme.test" })).toBeVisible();
  });

  it("test_RF_TEN_04_loading_shows_skeleton_rows_and_no_actions", () => {
    network.respond = () => new Promise<Response>(() => undefined);
    renderPage();

    const status = screen.getByRole("status", { name: MEMBERS_TEXTS.loading });
    expect(status.querySelectorAll('[data-skeleton="row"]')).toHaveLength(5);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: MEMBERS_TEXTS.changeRole })).toBeNull();
  });

  it("test_RF_TEN_04_no_request_without_a_company", () => {
    vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(null));
    renderPage();

    expect(screen.getByRole("status", { name: MEMBERS_TEXTS.loading })).toBeVisible();
    expect(network.requests).toHaveLength(0);
  });

  it("test_RF_TEN_02_dialog_closes_on_company_switch_and_does_not_come_back", async () => {
    network.respond = backend([ANA]);
    const view = renderPage();
    const ana = await rowOf("ana@acme.test");
    await userEvent.click(within(ana).getByRole("button", { name: MEMBERS_TEXTS.revoke }));
    expect(screen.getByRole("dialog")).toBeVisible();

    const switchTo = (organizationId: string) => {
      vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(organizationId));
      view.rerender();
    };
    switchTo(BETA.id);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Back to the first company: the dialog opened there is gone, not just hidden.
    switchTo(ACME.id);
    await rowOf("ana@acme.test");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

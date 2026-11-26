import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MembersPage from "@/app/(dashboard)/configuracion/colaboradores/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import { ROLE_LABELS } from "../lib/role-labels";
import { problem } from "./branches.test-helpers";
import { INVITATIONS_TEXTS } from "./InvitationsTable";
import { backend, DUENA, NUEVA, type Respond } from "./invitations.test-helpers";
import { COLLABORATORS_TEXTS } from "./MembersScreen";
import { MEMBERS_TEXTS } from "./MembersTable";
import { ACME, activeOrganizationResult } from "./tenancy.test-helpers";

// Configuración → Colaboradores, the tabs and "Invitaciones pendientes" (RF-TEN-05, spec §14,
// design.md §3.9): the screen talks to a fake BFF through the real api-client, so what is checked
// is what goes on the wire (path, company header) and what the screen shows from the backend's
// answers: each row's actions come only from its `allowed_actions`, and "Invitar" only from the
// company's `allowed_actions` and `invitable_roles`, never from a role.
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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MembersPage />
    </QueryClientProvider>,
  );
}

async function openInvitationsTab() {
  await userEvent.click(screen.getByRole("tab", { name: COLLABORATORS_TEXTS.tabs.invitations }));
}

async function rowOf(email: string): Promise<HTMLElement> {
  const cell = await screen.findByRole("cell", { name: email });
  return cell.closest("tr")!;
}

function invitationReads(): Request[] {
  return network.requests.filter(
    (request) => new URL(request.url).pathname === "/api/invitations/",
  );
}

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
  network.respond = () => new Response(null, { status: 500 });
});

describe("Colaboradores: invitaciones pendientes (RF-TEN-05, spec §14, design.md §3.9)", () => {
  it("test_RF_TEN_05_tabs_start_on_members_and_read_invitations_only_when_opened", async () => {
    network.respond = backend();
    renderPage();

    const members = screen.getByRole("tab", { name: COLLABORATORS_TEXTS.tabs.members });
    expect(members).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("cell", { name: "yo@acme.test" })).toBeVisible();
    expect(invitationReads()).toHaveLength(0);

    await openInvitationsTab();
    expect(screen.getByRole("tabpanel")).toBeVisible();
    const nueva = await rowOf("nueva@acme.test");
    expect(within(nueva).getByText(ROLE_LABELS.operator)).toBeVisible();
    expect(nueva).toHaveTextContent("Yo Mismo");
    // Q-232: the role code is never shown; the members filter belongs to the other tab.
    expect(screen.queryByText("operator")).toBeNull();
    expect(screen.queryByRole("button", { name: MEMBERS_TEXTS.filters.active })).toBeNull();

    const [list] = invitationReads();
    expect(list!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
  });

  it("test_RF_TEN_05_row_actions_follow_allowed_actions", async () => {
    network.respond = backend({
      invitations: () => [
        NUEVA,
        DUENA,
        { ...NUEVA, id: "x", email: "solo@acme.test", allowed_actions: ["invitation.revoke"] },
      ],
    });
    renderPage();
    await openInvitationsTab();

    const nueva = await rowOf("nueva@acme.test");
    expect(within(nueva).getByRole("button", { name: INVITATIONS_TEXTS.resend })).toBeVisible();
    expect(within(nueva).getByRole("button", { name: INVITATIONS_TEXTS.revoke })).toBeVisible();
    // An owner invitation the backend lets no action on, issued by no member.
    const duena = await rowOf("duena@acme.test");
    expect(within(duena).queryByRole("button")).toBeNull();
    expect(within(duena).getByText(INVITATIONS_TEXTS.missing)).toBeVisible();
    expect(within(duena).getByText(ROLE_LABELS.owner)).toBeVisible();
    const solo = await rowOf("solo@acme.test");
    expect(within(solo).queryByRole("button", { name: INVITATIONS_TEXTS.resend })).toBeNull();
    expect(within(solo).getByRole("button", { name: INVITATIONS_TEXTS.revoke })).toBeVisible();
  });

  it("test_RF_TEN_05_without_any_action_there_is_no_actions_column", async () => {
    network.respond = backend({ invitations: () => [DUENA] });
    renderPage();
    await openInvitationsTab();

    await rowOf("duena@acme.test");
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
  });

  it("test_RF_TEN_05_empty_state", async () => {
    network.respond = backend({ invitations: () => [] });
    renderPage();
    await openInvitationsTab();

    expect(await screen.findByRole("region", { name: INVITATIONS_TEXTS.empty })).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("test_AC_TEN_34_forbidden_shows_no_permission", async () => {
    const base = backend();
    network.respond = (request) =>
      new URL(request.url).pathname === "/api/invitations/"
        ? problem(403, "forbidden", "Acción no permitida")
        : base(request);
    renderPage();
    await openInvitationsTab();

    expect(await screen.findByRole("region", { name: INVITATIONS_TEXTS.forbidden })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Reintentar" })).toBeNull();
  });

  it("test_RF_TEN_05_error_retries_the_same_request", async () => {
    let fail = true;
    const base = backend();
    network.respond = (request) =>
      fail && new URL(request.url).pathname === "/api/invitations/"
        ? problem(500, "internal_error", "Error interno")
        : base(request);
    renderPage();
    await openInvitationsTab();

    expect(await screen.findByText("Error interno")).toBeVisible();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("cell", { name: "nueva@acme.test" })).toBeVisible();
  });

  it("test_RF_TEN_05_loading_shows_skeleton_rows_and_no_actions", async () => {
    const base = backend();
    network.respond = (request) =>
      new URL(request.url).pathname === "/api/invitations/"
        ? new Promise<Response>(() => undefined)
        : base(request);
    renderPage();
    await openInvitationsTab();

    const status = screen.getByRole("status", { name: INVITATIONS_TEXTS.loading });
    expect(status.querySelectorAll('[data-skeleton="row"]')).toHaveLength(5);
    expect(screen.queryByRole("button", { name: INVITATIONS_TEXTS.revoke })).toBeNull();
  });

  it("test_RF_TEN_05_invite_shows_with_invitation_create_and_invitable_roles", async () => {
    network.respond = backend();
    renderPage();
    expect(await screen.findByRole("button", { name: COLLABORATORS_TEXTS.invite })).toBeVisible();
  });

  it.each([
    [
      "without invitation.create",
      { allowed: ["org.read", "member.list"] as const, invitable: ["viewer"] as const },
    ],
    ["without invitable roles", { allowed: undefined, invitable: [] as const }],
  ])("test_RF_TEN_05_invite_is_hidden_%s", async (_case, { allowed, invitable }) => {
    network.respond = backend({ allowed: allowed && [...allowed], invitable: [...invitable] });
    renderPage();
    await screen.findByRole("cell", { name: "yo@acme.test" });
    // The details answered too: what is checked is the screen after both lists.
    await vi.waitFor(() =>
      expect(
        network.requests.some((r) => new URL(r.url).pathname === "/api/organizations/current/"),
      ).toBe(true),
    );
    expect(screen.queryByRole("button", { name: COLLABORATORS_TEXTS.invite })).toBeNull();
  });

  it.each([
    ["load", () => new Promise<Response>(() => undefined)],
    ["fail", () => problem(500, "internal_error", "Error interno")],
  ])("test_RF_TEN_05_invite_fails_closed_while_details_%s", async (_case, details) => {
    const base = backend();
    network.respond = (request) =>
      new URL(request.url).pathname === "/api/organizations/current/" ? details() : base(request);
    renderPage();
    await screen.findByRole("cell", { name: "yo@acme.test" });
    await vi.waitFor(() =>
      expect(
        network.requests.some((r) => new URL(r.url).pathname === "/api/organizations/current/"),
      ).toBe(true),
    );
    expect(screen.queryByRole("button", { name: COLLABORATORS_TEXTS.invite })).toBeNull();
  });
});

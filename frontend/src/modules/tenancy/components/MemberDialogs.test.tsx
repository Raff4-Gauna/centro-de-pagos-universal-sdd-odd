import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MembersPage from "@/app/(dashboard)/configuracion/colaboradores/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { Member } from "../hooks/useMembers";
import type { MyOrganization } from "../lib/active-organization";
import { LAST_OWNER_TEXT } from "../lib/member-errors";
import { ROLE_LABELS } from "../lib/role-labels";
import { json, problem } from "./branches.test-helpers";
import { MEMBER_EXIT_TEXTS } from "./MemberExitDialog";
import { MEMBER_ROLE_TEXTS } from "./MemberRoleDialog";
import { ANA, ME, membersAnswer } from "./members.test-helpers";
import { MEMBERS_TEXTS } from "./MembersTable";
import { ACME, activeOrganizationResult, BETA } from "./tenancy.test-helpers";

// The dialogs of "Colaboradores" (RF-TEN-04, design.md §4.2, §6): what each write sends, that it
// names the company the dialog was opened for, that the screen changes only after the backend's
// `2xx`, and how each refusal is told (`409 last_owner`, `503 organization_busy`, Q-230).
type Respond = (request: Request) => Response | Promise<Response>;
const network = vi.hoisted(() => ({
  respond: (() => new Response(null, { status: 500 })) as Respond,
  requests: [] as Request[],
}));
const router = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));
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

type Write = (request: Request) => Response | null;

// The fake backend: the members list, the person's companies, and `write` for the rest.
function backend(
  members: readonly Member[],
  write: Write,
  organizations: MyOrganization[] = [BETA],
): Respond {
  return (request) => {
    const { pathname } = new URL(request.url);
    if (request.method === "GET" && pathname === "/api/memberships/") {
      return membersAnswer(request, members);
    }
    if (pathname === "/api/organizations/") {
      return json({
        count: organizations.length,
        next: null,
        previous: null,
        results: organizations,
      });
    }
    if (pathname === "/api/organizations/current/") return problem(503, "x", "No disponible");
    return write(request) ?? problem(404, "not_found", "No encontrado");
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MembersPage />
    </QueryClientProvider>,
  );
}

async function open(email: string, action: string): Promise<HTMLElement> {
  const cell = await screen.findByRole("cell", { name: email });
  await userEvent.click(within(cell.closest("tr")!).getByRole("button", { name: action }));
  return screen.getByRole("dialog");
}

function writes(): Request[] {
  return network.requests.filter((request) => request.method !== "GET");
}

function listReads(): number {
  return network.requests.filter(
    (request) => request.method === "GET" && new URL(request.url).pathname === "/api/memberships/",
  ).length;
}

async function pickRole(dialog: HTMLElement, label: string) {
  await userEvent.click(within(dialog).getByRole("combobox", { name: MEMBER_ROLE_TEXTS.newRole }));
  await userEvent.click(screen.getByRole("option", { name: label }));
}

const noContent = () => new Response(null, { status: 204 });

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
  network.respond = () => new Response(null, { status: 500 });
  router.replace.mockReset();
});

describe("Colaboradores: diálogos (RF-TEN-04, design.md §4.2)", () => {
  it("test_RF_TEN_04_change_role_sends_the_role_and_closes_after_200", async () => {
    network.respond = backend([ANA], (request) =>
      request.method === "PATCH" ? json({ ...ANA, role: "admin" }) : null,
    );
    renderPage();

    const dialog = await open("ana@acme.test", MEMBERS_TEXTS.changeRole);
    const confirm = within(dialog).getByRole("button", { name: MEMBER_ROLE_TEXTS.confirm });
    // Nothing picked yet: confirming is always a choice.
    expect(confirm).toBeDisabled();
    await pickRole(dialog, ROLE_LABELS.admin);
    const reads = listReads();
    await userEvent.click(confirm);

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [patch] = writes();
    expect(new URL(patch!.url).pathname).toBe(`/api/memberships/${ANA.id}/`);
    expect(patch!.method).toBe("PATCH");
    expect(patch!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    expect(await patch!.json()).toEqual({ role: "admin" });
    await waitFor(() => expect(listReads()).toBeGreaterThan(reads));
  });

  it("test_AC_TEN_13_change_role_last_owner_is_explained_and_stays_open", async () => {
    network.respond = backend([ME], (request) =>
      request.method === "PATCH"
        ? problem(409, "last_owner", "Último owner", {
            detail: "La organización tiene que conservar al menos un owner.",
          })
        : null,
    );
    renderPage();

    const dialog = await open("yo@acme.test", MEMBERS_TEXTS.changeRole);
    await pickRole(dialog, ROLE_LABELS.viewer);
    await userEvent.click(within(dialog).getByRole("button", { name: MEMBER_ROLE_TEXTS.confirm }));

    expect(await within(dialog).findByText(LAST_OWNER_TEXT)).toBeVisible();
    expect(screen.getByRole("dialog")).toBeVisible();
    // The role code of the backend's detail is never shown (Q-232).
    expect(within(dialog).queryByText(/owner/)).toBeNull();
  });

  it("test_Q_230_busy_organization_shows_its_text_and_lets_retry", async () => {
    let answers = 0;
    network.respond = backend([ANA], (request) => {
      if (request.method !== "DELETE") return null;
      answers += 1;
      return answers === 1
        ? problem(503, "organization_busy", "Hay otra operación en curso, probá de nuevo")
        : noContent();
    });
    renderPage();

    const dialog = await open("ana@acme.test", MEMBERS_TEXTS.revoke);
    const confirm = within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.revoke.confirm });
    await userEvent.click(confirm);
    expect(
      await within(dialog).findByText("Hay otra operación en curso, probá de nuevo"),
    ).toBeVisible();
    expect(confirm).toBeEnabled();

    await userEvent.click(confirm);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(writes()).toHaveLength(2);
  });

  it("test_RF_TEN_04_revoke_deletes_the_membership_and_rereads_the_list", async () => {
    network.respond = backend([ANA], (request) =>
      request.method === "DELETE" ? noContent() : null,
    );
    renderPage();

    const dialog = await open("ana@acme.test", MEMBERS_TEXTS.revoke);
    expect(dialog).toHaveAccessibleName(MEMBER_EXIT_TEXTS.revoke.title("Ana Pérez"));
    const reads = listReads();
    await userEvent.click(
      within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.revoke.confirm }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [revoke] = writes();
    expect(revoke!.method).toBe("DELETE");
    expect(new URL(revoke!.url).pathname).toBe(`/api/memberships/${ANA.id}/`);
    expect(revoke!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    await waitFor(() => expect(listReads()).toBeGreaterThan(reads));
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("test_AC_TEN_31_leave_drops_the_company_and_goes_home", async () => {
    network.respond = backend([ME], (request) => (request.method === "POST" ? noContent() : null));
    renderPage();

    const dialog = await open("yo@acme.test", MEMBERS_TEXTS.leave);
    const reads = listReads();
    await userEvent.click(
      within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.leave.confirm }),
    );

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/inicio"));
    const [leave] = writes();
    expect(new URL(leave!.url).pathname).toBe("/api/memberships/me/leave/");
    expect(leave!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    // The person's companies are read again after the `204`, never before.
    const companies = network.requests.findIndex(
      (request) => new URL(request.url).pathname === "/api/organizations/",
    );
    expect(companies).toBeGreaterThan(network.requests.indexOf(leave!));
    // The members of the company left are not read again (that would be a `404`).
    expect(listReads()).toBe(reads);
  });

  it("test_AC_TEN_31_leaving_the_last_company_goes_to_sin_organizacion", async () => {
    network.respond = backend(
      [ME],
      (request) => (request.method === "POST" ? noContent() : null),
      [],
    );
    renderPage();

    const dialog = await open("yo@acme.test", MEMBERS_TEXTS.leave);
    await userEvent.click(
      within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.leave.confirm }),
    );

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/sin-organizacion"));
  });

  it("test_AC_TEN_13_leave_last_owner_is_explained_and_nothing_moves", async () => {
    network.respond = backend([ME], (request) =>
      request.method === "POST" ? problem(409, "last_owner", "Último owner") : null,
    );
    renderPage();

    const dialog = await open("yo@acme.test", MEMBERS_TEXTS.leave);
    await userEvent.click(
      within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.leave.confirm }),
    );

    expect(await within(dialog).findByText(LAST_OWNER_TEXT)).toBeVisible();
    expect(router.replace).not.toHaveBeenCalled();
    expect(
      network.requests.some((request) => new URL(request.url).pathname === "/api/organizations/"),
    ).toBe(false);
  });

  it("test_RF_TEN_04_cancel_sends_nothing", async () => {
    network.respond = backend([ANA], () => noContent());
    renderPage();

    const dialog = await open("ana@acme.test", MEMBERS_TEXTS.revoke);
    await userEvent.click(within(dialog).getByRole("button", { name: MEMBER_EXIT_TEXTS.cancel }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(writes()).toHaveLength(0);
  });
});

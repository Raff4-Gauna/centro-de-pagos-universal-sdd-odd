import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MembersPage from "@/app/(dashboard)/configuracion/colaboradores/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { Invitation } from "../hooks/useInvitations";
import { INVITATION_ERROR_TEXTS } from "../lib/invitation-errors";
import { json, problem } from "./branches.test-helpers";
import { INVITATION_DIALOG_TEXTS } from "./InvitationDialogs";
import { INVITATION_LINK_TEXTS } from "./InvitationLinkDialog";
import { INVITATIONS_TEXTS } from "./InvitationsTable";
import {
  acceptUrl,
  backend,
  created,
  keptByTheTab,
  NUEVA,
  RESENT_TOKEN,
  type Respond,
  type Write,
} from "./invitations.test-helpers";
import { COLLABORATORS_TEXTS } from "./MembersScreen";
import { ACME, activeOrganizationResult } from "./tenancy.test-helpers";

// "Reenviar" and "Revocar" of a pending invitation (RF-TEN-05, RN-TEN-12, AC-TEN-24, design.md
// §4.3): what each write sends and to which company, that resending shows the new link once and
// keeps it out of TanStack Query, that revoking closes only after the backend's `200`, and how a
// refusal is told.
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

const RESEND_PATH = `/api/invitations/${NUEVA.id}/resend/`;
const REVOKE_PATH = `/api/invitations/${NUEVA.id}/revoke/`;
const RESENT: Invitation = { ...NUEVA, id: "8b9c0d1e-2f3a-4b4c-8d5e-6f7a8b9c0d1e" };

function on(path: string, answer: () => Response | Promise<Response>): Write {
  return (request) =>
    request.method === "POST" && new URL(request.url).pathname === path ? answer() : null;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MembersPage />
    </QueryClientProvider>,
  );
  return queryClient;
}

async function open(action: string): Promise<HTMLElement> {
  await userEvent.click(screen.getByRole("tab", { name: COLLABORATORS_TEXTS.tabs.invitations }));
  const cell = await screen.findByRole("cell", { name: NUEVA.email });
  await userEvent.click(within(cell.closest("tr")!).getByRole("button", { name: action }));
  return screen.getByRole("dialog");
}

function writes(): Request[] {
  return network.requests.filter((request) => request.method !== "GET");
}

function listReads(): number {
  return network.requests.filter(
    (r) => r.method === "GET" && new URL(r.url).pathname === "/api/invitations/",
  ).length;
}

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
  network.respond = () => new Response(null, { status: 500 });
});

describe("Reenviar y revocar invitaciones (RF-TEN-05, RN-TEN-12, AC-TEN-24)", () => {
  it("test_AC_TEN_24_resend_shows_the_new_link_once_outside_the_query_cache", async () => {
    let list: Invitation[] = [NUEVA];
    network.respond = backend({
      invitations: () => list,
      write: on(RESEND_PATH, () => {
        list = [RESENT];
        return created(RESENT, RESENT_TOKEN);
      }),
    });
    const queryClient = renderPage();
    const dialog = await open(INVITATIONS_TEXTS.resend);
    expect(dialog).toHaveAccessibleName(INVITATION_DIALOG_TEXTS.resend.title(NUEVA.email));
    await userEvent.click(
      within(dialog).getByRole("button", { name: INVITATION_DIALOG_TEXTS.resend.confirm }),
    );

    const link = await screen.findByRole("dialog", { name: INVITATION_LINK_TEXTS.title });
    expect(within(link).getByRole("textbox", { name: INVITATION_LINK_TEXTS.field })).toHaveValue(
      acceptUrl(RESENT_TOKEN),
    );
    const [request] = writes();
    expect(new URL(request!.url).pathname).toBe(RESEND_PATH);
    expect(request!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    await waitFor(() => expect(listReads()).toBe(2));
    expect(keptByTheTab(queryClient)).not.toContain(RESENT_TOKEN);

    await userEvent.click(within(link).getByRole("button", { name: INVITATION_LINK_TEXTS.done }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body.textContent).not.toContain(RESENT_TOKEN);
  });

  it("test_RN_TEN_12_resend_of_an_invitation_no_longer_pending_is_explained", async () => {
    network.respond = backend({
      write: on(RESEND_PATH, () => problem(409, "invalid_transition", "Transición inválida")),
    });
    renderPage();
    const dialog = await open(INVITATIONS_TEXTS.resend);
    await userEvent.click(
      within(dialog).getByRole("button", { name: INVITATION_DIALOG_TEXTS.resend.confirm }),
    );

    expect(
      await within(dialog).findByText(INVITATION_ERROR_TEXTS.invalid_transition),
    ).toBeVisible();
    expect(screen.queryByRole("dialog", { name: INVITATION_LINK_TEXTS.title })).toBeNull();
    await waitFor(() => expect(listReads()).toBe(2));
  });

  it("test_RF_TEN_05_revoke_closes_after_the_backend_answer_and_reads_the_list", async () => {
    let list: Invitation[] = [NUEVA];
    let answer: (response: Response) => void = () => undefined;
    network.respond = backend({
      invitations: () => list,
      write: on(
        REVOKE_PATH,
        () =>
          new Promise<Response>((resolve) => {
            answer = resolve;
          }),
      ),
    });
    renderPage();
    const dialog = await open(INVITATIONS_TEXTS.revoke);
    expect(dialog).toHaveAccessibleName(INVITATION_DIALOG_TEXTS.revoke.title(NUEVA.email));
    await userEvent.click(
      within(dialog).getByRole("button", { name: INVITATION_DIALOG_TEXTS.revoke.confirm }),
    );

    // Until the backend answers the dialog stays and the row too.
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: INVITATION_DIALOG_TEXTS.cancel }),
    ).toBeDisabled();
    list = [];
    answer(json({ ...NUEVA, status: "revoked", allowed_actions: [] }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByRole("region", { name: INVITATIONS_TEXTS.empty })).toBeVisible();
    const [request] = writes();
    expect(new URL(request!.url).pathname).toBe(REVOKE_PATH);
    expect(request!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
  });

  it("test_RF_TEN_05_revoke_refusal_stays_in_the_dialog", async () => {
    network.respond = backend({
      write: on(REVOKE_PATH, () =>
        problem(503, "organization_busy", "Hay otra operación en curso, probá de nuevo"),
      ),
    });
    renderPage();
    const dialog = await open(INVITATIONS_TEXTS.revoke);
    await userEvent.click(
      within(dialog).getByRole("button", { name: INVITATION_DIALOG_TEXTS.revoke.confirm }),
    );

    expect(
      await within(dialog).findByText("Hay otra operación en curso, probá de nuevo"),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: INVITATION_DIALOG_TEXTS.revoke.confirm }),
    ).toBeEnabled();
  });
});

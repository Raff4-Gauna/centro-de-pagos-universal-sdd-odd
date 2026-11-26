import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MembersPage from "@/app/(dashboard)/configuracion/colaboradores/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import { INVITATION_ERROR_TEXTS } from "../lib/invitation-errors";
import { INVITE_FORM_ERRORS } from "../lib/invite-form";
import { ROLE_LABELS } from "../lib/role-labels";
import { problem } from "./branches.test-helpers";
import { INVITATION_LINK_TEXTS } from "./InvitationLinkDialog";
import {
  acceptUrl,
  backend,
  created,
  keptByTheTab,
  NUEVA,
  type Respond,
  TOKEN,
  type Write,
} from "./invitations.test-helpers";
import { INVITE_TEXTS } from "./InviteDialog";
import { COLLABORATORS_TEXTS } from "./MembersScreen";
import { ACME, activeOrganizationResult, BETA } from "./tenancy.test-helpers";

// "Invitar" and the link shown once (RF-TEN-05, AC-TEN-24, Q-207, design.md §3.9): what the form
// sends and checks, the roles it offers (`invitable_roles`), how each refusal is told, and that the
// link with the token lives only in the dialog: never in TanStack Query, storage or the address,
// and gone on closing or switching company.
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

const isCreate = (request: Request) =>
  request.method === "POST" && new URL(request.url).pathname === "/api/invitations/";

function inviting(answer: (request: Request) => Response | Promise<Response>): Write {
  return (request) => (isCreate(request) ? answer(request) : null);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page = () => (
    <QueryClientProvider client={queryClient}>
      <MembersPage />
    </QueryClientProvider>
  );
  const view = render(page());
  return { queryClient, rerender: () => view.rerender(page()) };
}

async function openInvite(): Promise<HTMLElement> {
  await userEvent.click(await screen.findByRole("button", { name: COLLABORATORS_TEXTS.invite }));
  return screen.getByRole("dialog", { name: INVITE_TEXTS.title });
}

async function fill(dialog: HTMLElement, email: string, role?: string) {
  await userEvent.type(within(dialog).getByRole("textbox", { name: INVITE_TEXTS.email }), email);
  if (role !== undefined) {
    await userEvent.click(within(dialog).getByRole("combobox", { name: INVITE_TEXTS.role }));
    await userEvent.click(screen.getByRole("option", { name: role }));
  }
}

async function submit(dialog: HTMLElement) {
  await userEvent.click(within(dialog).getByRole("button", { name: INVITE_TEXTS.confirm }));
}

function creates(): Request[] {
  return network.requests.filter(isCreate);
}

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
  network.respond = () => new Response(null, { status: 500 });
  window.sessionStorage.clear();
  window.localStorage.clear();
});

describe("Invitar y link de una sola vez (RF-TEN-05, AC-TEN-24, Q-207)", () => {
  it("test_RF_TEN_05_roles_offered_are_exactly_invitable_roles", async () => {
    network.respond = backend({ invitable: ["operator", "viewer"] });
    renderPage();
    const dialog = await openInvite();

    await userEvent.click(within(dialog).getByRole("combobox", { name: INVITE_TEXTS.role }));
    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual([ROLE_LABELS.operator, ROLE_LABELS.viewer]);
  });

  it("test_RF_TEN_05_form_checks_before_sending", async () => {
    network.respond = backend();
    renderPage();
    const dialog = await openInvite();

    await submit(dialog);
    expect(await within(dialog).findByText(INVITE_FORM_ERRORS.emailRequired)).toBeVisible();
    expect(within(dialog).getByText(INVITE_FORM_ERRORS.roleRequired)).toBeVisible();

    await fill(dialog, "no es un email");
    await submit(dialog);
    expect(await within(dialog).findByText(INVITE_FORM_ERRORS.emailInvalid)).toBeVisible();
    expect(creates()).toHaveLength(0);
  });

  it("test_RF_TEN_05_sends_trimmed_email_and_role_to_the_dialogs_company", async () => {
    network.respond = backend({ write: inviting(() => created(NUEVA, TOKEN)) });
    renderPage();
    const dialog = await openInvite();
    await fill(dialog, "  nueva@acme.test ", ROLE_LABELS.operator);
    await submit(dialog);

    await screen.findByRole("dialog", { name: INVITATION_LINK_TEXTS.title });
    const [request] = creates();
    expect(request!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    expect(await request!.json()).toEqual({ email: "nueva@acme.test", role: "operator" });
  });

  it("test_AC_TEN_24_link_shown_once_and_kept_out_of_the_query_cache", async () => {
    network.respond = backend({ write: inviting(() => created(NUEVA, TOKEN)) });
    const { queryClient } = renderPage();
    const dialog = await openInvite();
    await fill(dialog, "nueva@acme.test", ROLE_LABELS.operator);
    const reads = (path: string) =>
      network.requests.filter((r) => r.method === "GET" && new URL(r.url).pathname === path).length;
    const CURRENT = "/api/organizations/current/";
    const before = reads(CURRENT);
    await submit(dialog);

    const link = await screen.findByRole("dialog", { name: INVITATION_LINK_TEXTS.title });
    expect(within(link).getByRole("textbox", { name: INVITATION_LINK_TEXTS.field })).toHaveValue(
      acceptUrl(TOKEN),
    );
    expect(within(link).getByText(INVITATION_LINK_TEXTS.once)).toBeVisible();
    // The company's details were read again after the `201`: what the tab keeps now has no token.
    await waitFor(() => expect(reads(CURRENT)).toBeGreaterThan(before));
    // The mutation is kept, with the invitation it returned, but without the link.
    const [mutation] = queryClient.getMutationCache().getAll();
    expect(mutation!.state.data).toMatchObject({ id: NUEVA.id, email: NUEVA.email });
    expect(keptByTheTab(queryClient)).not.toContain(TOKEN);

    // Closing discards it: nothing shows it again, and the list read afterwards has no token.
    await userEvent.click(within(link).getByRole("button", { name: INVITATION_LINK_TEXTS.done }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body.textContent).not.toContain(TOKEN);
    await userEvent.click(screen.getByRole("tab", { name: COLLABORATORS_TEXTS.tabs.invitations }));
    expect(await screen.findByRole("cell", { name: NUEVA.email })).toBeVisible();
    expect(keptByTheTab(queryClient)).not.toContain(TOKEN);
  });

  it("test_AC_TEN_24_copy_writes_the_link_to_the_clipboard", async () => {
    const user = userEvent.setup();
    network.respond = backend({ write: inviting(() => created(NUEVA, TOKEN)) });
    renderPage();
    await user.click(await screen.findByRole("button", { name: COLLABORATORS_TEXTS.invite }));
    const dialog = screen.getByRole("dialog", { name: INVITE_TEXTS.title });
    await user.type(
      within(dialog).getByRole("textbox", { name: INVITE_TEXTS.email }),
      "nueva@acme.test",
    );
    await user.click(within(dialog).getByRole("combobox", { name: INVITE_TEXTS.role }));
    await user.click(screen.getByRole("option", { name: ROLE_LABELS.operator }));
    await user.click(within(dialog).getByRole("button", { name: INVITE_TEXTS.confirm }));

    const link = await screen.findByRole("dialog", { name: INVITATION_LINK_TEXTS.title });
    await user.click(within(link).getByRole("button", { name: INVITATION_LINK_TEXTS.copy }));
    expect(await within(link).findByText(INVITATION_LINK_TEXTS.copied)).toBeVisible();
    expect(await navigator.clipboard.readText()).toBe(acceptUrl(TOKEN));
  });

  it("test_AC_TEN_24_copy_refused_says_to_copy_by_hand", async () => {
    const user = userEvent.setup();
    network.respond = backend({ write: inviting(() => created(NUEVA, TOKEN)) });
    renderPage();
    await user.click(await screen.findByRole("button", { name: COLLABORATORS_TEXTS.invite }));
    const dialog = screen.getByRole("dialog", { name: INVITE_TEXTS.title });
    await user.type(
      within(dialog).getByRole("textbox", { name: INVITE_TEXTS.email }),
      "nueva@acme.test",
    );
    await user.click(within(dialog).getByRole("combobox", { name: INVITE_TEXTS.role }));
    await user.click(screen.getByRole("option", { name: ROLE_LABELS.operator }));
    await user.click(within(dialog).getByRole("button", { name: INVITE_TEXTS.confirm }));

    const link = await screen.findByRole("dialog", { name: INVITATION_LINK_TEXTS.title });
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("denied"));
    await user.click(within(link).getByRole("button", { name: INVITATION_LINK_TEXTS.copy }));
    expect(await within(link).findByText(INVITATION_LINK_TEXTS.copyFailed)).toBeVisible();
  });

  it("test_AC_TEN_24_company_switch_discards_the_link", async () => {
    network.respond = backend({ write: inviting(() => created(NUEVA, TOKEN)) });
    const view = renderPage();
    const dialog = await openInvite();
    await fill(dialog, "nueva@acme.test", ROLE_LABELS.operator);
    await submit(dialog);
    await screen.findByRole("dialog", { name: INVITATION_LINK_TEXTS.title });

    const switchTo = (organizationId: string) => {
      vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(organizationId));
      view.rerender();
    };
    switchTo(BETA.id);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    switchTo(ACME.id);
    await screen.findByRole("button", { name: COLLABORATORS_TEXTS.invite });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body.textContent).not.toContain(TOKEN);
  });

  it.each([
    ["already_member", 409, INVITATION_ERROR_TEXTS.already_member],
    ["invitation_pending", 409, INVITATION_ERROR_TEXTS.invitation_pending],
    ["organization_busy", 503, "Hay otra operación en curso, probá de nuevo"],
    ["forbidden", 403, "Acción no permitida"],
  ])("test_RF_TEN_05_refusal_%s_stays_in_the_dialog", async (code, status, text) => {
    const title = code === "invitation_pending" ? "Conflict" : text;
    network.respond = backend({ write: inviting(() => problem(status, code, title)) });
    renderPage();
    const dialog = await openInvite();
    await fill(dialog, "nueva@acme.test", ROLE_LABELS.operator);
    await submit(dialog);

    expect(await within(dialog).findByText(text)).toBeVisible();
    expect(screen.queryByRole("dialog", { name: INVITATION_LINK_TEXTS.title })).toBeNull();
    // Retrying is the person's choice: the same form, enabled again.
    expect(within(dialog).getByRole("button", { name: INVITE_TEXTS.confirm })).toBeEnabled();
  });

  it("test_RF_TEN_05_validation_error_goes_under_its_field", async () => {
    network.respond = backend({
      write: inviting(() =>
        problem(400, "validation_error", "Datos inválidos", {
          errors: [{ field: "email", code: "invalid", message: "Tiene que ser un email válido." }],
        }),
      ),
    });
    renderPage();
    const dialog = await openInvite();
    await fill(dialog, "raro@dominio", ROLE_LABELS.operator);
    await submit(dialog);

    const field = within(dialog).getByRole("textbox", { name: INVITE_TEXTS.email });
    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(within(dialog).getByText("Tiene que ser un email válido.")).toBeVisible();
    expect(within(dialog).queryByText("Datos inválidos")).toBeNull();
  });

  it("test_RF_TEN_05_a_2xx_without_link_is_an_error_not_a_link", async () => {
    network.respond = backend({
      write: inviting(
        () =>
          new Response(JSON.stringify(NUEVA), {
            status: 201,
            headers: { "content-type": "application/json" },
          }),
      ),
    });
    renderPage();
    const dialog = await openInvite();
    await fill(dialog, "nueva@acme.test", ROLE_LABELS.operator);
    await submit(dialog);

    expect(await within(dialog).findByText("Respuesta inesperada del servidor")).toBeVisible();
    expect(screen.queryByRole("dialog", { name: INVITATION_LINK_TEXTS.title })).toBeNull();
  });
});

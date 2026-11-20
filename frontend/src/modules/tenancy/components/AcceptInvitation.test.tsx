import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER, ORGANIZATION_HEADER } from "@/lib/api-client";

import { HOME_PATH } from "../context/ActiveOrgProvider";
import { MY_INVITATIONS_QUERY_KEY } from "../hooks/useMyInvitations";
import { ORGANIZATIONS_QUERY_KEY } from "../hooks/useOrganizations";
import { clearTabOrganization, readTabOrganization } from "../lib/active-organization";
import { INVITATION_TOKEN_KEY } from "../lib/invitation-token";
import {
  ACCEPT_INVITATION_TEXTS as TEXTS,
  AcceptInvitation,
  LOGIN_FOR_INVITATION,
} from "./AcceptInvitation";

// AC-TEN-17 (UI), AC-TEN-18/19, design.md §3.9: the screen talks to a fake BFF through the real
// api-client, so what is checked is what goes on the wire (path, body, CSRF, no company header),
// what the screen shows only after the backend answered, and that the token is left neither in
// the URL nor in `sessionStorage`. Obviously fake token.
type Respond = (request: Request) => Response | Promise<Response>;
const network = vi.hoisted(() => ({
  respond: (() => new Response(null, { status: 500 })) as Respond,
  requests: [] as Request[],
  sessionExpired: [] as string[],
}));

vi.mock("next/navigation", () => ({ useRouter: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  // A browser resolves a relative URL against the page; Node's Request (under jsdom) does not.
  class BrowserRequest extends Request {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
    }
  }
  return {
    ...actual,
    apiClient: actual.createApiClient({
      Request: BrowserRequest,
      readCsrfToken: () => "csrf-test-token",
      onSessionExpired: (url) => {
        network.sessionExpired.push(url);
      },
      onOrganizationError: () => undefined,
      fetch: async (request: Request) => {
        network.requests.push(request.clone());
        return network.respond(request);
      },
    }),
  };
});

const TOKEN = "fake-invitation-token-for-tests";
const ACME_ID = "6a1f0c2e-1b3d-4e5f-8a9b-0c1d2e3f4a5b";
const ACCEPTED = {
  organization: { id: ACME_ID, name: "Acme" },
  role: "operator",
  membership_id: "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function problem(status: number, code: string, title: string, extra: object = {}): Response {
  return new Response(
    JSON.stringify({
      type: `urn:hub:problem:${code}`,
      title,
      status,
      code,
      detail: "detalle-que-no-se-muestra",
      request_id: "req-1",
      ...extra,
    }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

const invalid = (reason: string) =>
  problem(400, "invitation_invalid", "Invitación inválida", { reason });

let queryClient: QueryClient;
const push = vi.fn();
const replace = vi.fn();
let saveDefault: ReturnType<typeof vi.fn>;

function openLink(url = `/invitacion#token=${TOKEN}`) {
  window.history.replaceState(null, "", url);
}

function renderScreen(hasSession = true) {
  return render(
    <QueryClientProvider client={queryClient}>
      <AcceptInvitation hasSession={hasSession} />
    </QueryClientProvider>,
  );
}

function stored(): string | null {
  return window.sessionStorage.getItem(INVITATION_TOKEN_KEY);
}

// Q-233: a refusal's only way out is "Ir a Inicio", a link to `/inicio`; never "Reintentar".
function expectGoHomeOnly() {
  const home = screen.getByRole("link", { name: TEXTS.goHome });
  expect(home).toHaveAttribute("href", HOME_PATH);
  expect(HOME_PATH).toBe("/inicio");
  expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
}

function expectNoTokenLeft() {
  expect(window.location.href).not.toContain(TOKEN);
  expect(window.location.hash).toBe("");
  expect(stored()).toBeNull();
}

beforeEach(() => {
  network.requests.length = 0;
  network.sessionExpired.length = 0;
  network.respond = () => json(ACCEPTED);
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(useRouter).mockReturnValue({ push, replace } as unknown as ReturnType<
    typeof useRouter
  >);
  saveDefault = vi.fn(async () => new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", saveDefault);
  openLink();
});

afterEach(() => {
  window.sessionStorage.clear();
  clearTabOrganization();
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
  push.mockReset();
  replace.mockReset();
});

describe("AcceptInvitation (AC-TEN-17, design.md §3.9)", () => {
  it("test_AC_TEN_17_valid_invitation_is_accepted_only_after_the_backend", async () => {
    let answer: (response: Response) => void = () => undefined;
    network.respond = () => new Promise((resolve) => (answer = resolve));
    renderScreen();

    await waitFor(() => expect(network.requests).toHaveLength(1));
    expect(screen.getByRole("status", { name: TEXTS.loading })).toBeInTheDocument();
    expect(screen.queryByText(TEXTS.accepted)).not.toBeInTheDocument();
    const [request] = network.requests;
    expect(request!.method).toBe("POST");
    expect(new URL(request!.url).pathname).toBe("/api/invitations/accept/");
    expect(new URL(request!.url).search).toBe("");
    expect(await request!.json()).toEqual({ token: TOKEN });
    expect(request!.headers.get(CSRF_HEADER)).toBe("csrf-test-token");
    expect(request!.headers.get(ORGANIZATION_HEADER)).toBeNull();

    answer(json(ACCEPTED));
    expect(await screen.findByText(TEXTS.accepted)).toBeInTheDocument();
    expect(screen.getByText("Empresa: Acme")).toBeInTheDocument();
    expect(screen.getByText("Rol: Operador")).toBeInTheDocument();
    expect(screen.queryByText(/operator/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: TEXTS.goHome })).not.toBeInTheDocument();
    expectNoTokenLeft();
  });

  it("test_AC_TEN_17_go_to_organization_picks_it_for_the_tab_and_opens_home", async () => {
    queryClient.setQueryData(ORGANIZATIONS_QUERY_KEY, []);
    queryClient.setQueryData(MY_INVITATIONS_QUERY_KEY, []);
    renderScreen();
    await userEvent.click(await screen.findByRole("button", { name: TEXTS.goToOrganization }));

    expect(readTabOrganization()).toBe(ACME_ID);
    expect(push).toHaveBeenCalledWith(HOME_PATH);
    expect(saveDefault).toHaveBeenCalledTimes(1);
    // The lists are read again by the shell, never resolved from the old ones.
    expect(queryClient.getQueryData(ORGANIZATIONS_QUERY_KEY)).toBeUndefined();
    expect(queryClient.getQueryData(MY_INVITATIONS_QUERY_KEY)).toBeUndefined();
  });

  it.each([
    ["expired", TEXTS.expired],
    ["revoked", TEXTS.revoked],
    ["used", TEXTS.used],
    ["email_mismatch", TEXTS.otherAccount],
    ["not_found", TEXTS.notFound],
  ])("test_AC_TEN_17_refused_%s_shows_its_state_and_leaves_no_token", async (reason, text) => {
    network.respond = () => invalid(reason);
    renderScreen();
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.queryByText(TEXTS.accepted)).not.toBeInTheDocument();
    expect(screen.queryByText("detalle-que-no-se-muestra")).not.toBeInTheDocument();
    expectGoHomeOnly();
    expectNoTokenLeft();
  });

  it("test_AC_TEN_17_suspended_organization_shows_its_state", async () => {
    network.respond = () => problem(409, "organization_suspended", "Organización suspendida");
    renderScreen();
    expect(await screen.findByText(TEXTS.suspended)).toBeInTheDocument();
    expectGoHomeOnly();
    expectNoTokenLeft();
  });

  it.each([
    [problem(409, "already_member", "Ya es miembro"), "Ya es miembro"],
    [invalid("otro_motivo"), "Invitación inválida"],
  ])("test_AC_TEN_17_other_refusals_show_the_title_of_their_code", async (response, title) => {
    network.respond = () => response;
    renderScreen();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expectGoHomeOnly();
    expectNoTokenLeft();
  });

  it("test_AC_TEN_17_without_token_shows_not_found_and_sends_nothing", async () => {
    openLink("/invitacion");
    renderScreen();
    expect(await screen.findByText(TEXTS.notFound)).toBeInTheDocument();
    expectGoHomeOnly();
    expect(network.requests).toHaveLength(0);
    expect(replace).not.toHaveBeenCalled();
  });

  it("test_AC_TEN_17_without_session_token_waits_in_the_tab_and_login_comes_back", async () => {
    const view = renderScreen(false);
    await waitFor(() => expect(replace).toHaveBeenCalledWith(LOGIN_FOR_INVITATION));
    expect(LOGIN_FOR_INVITATION).toBe("/login?return_to=%2Finvitacion");
    expect(LOGIN_FOR_INVITATION).not.toContain(TOKEN);
    expect(network.requests).toHaveLength(0);
    expect(window.location.hash).toBe("");
    expect(stored()).toBe(TOKEN);
    view.unmount();

    // Back from "Ingresar": `/invitacion` without fragment, the token from the tab.
    window.history.replaceState(null, "", "/invitacion");
    renderScreen(true);
    expect(await screen.findByText(TEXTS.accepted)).toBeInTheDocument();
    expect(await network.requests[0]!.json()).toEqual({ token: TOKEN });
    expectNoTokenLeft();
  });

  it("test_AC_TEN_17_dead_session_keeps_the_token_for_after_the_login", async () => {
    network.respond = () => problem(401, "session_revoked", "Sesión revocada");
    renderScreen();
    await waitFor(() => expect(network.sessionExpired).toHaveLength(1));
    expect(network.sessionExpired[0]).not.toContain(TOKEN);
    expect(screen.getByRole("status", { name: TEXTS.loading })).toBeInTheDocument();
    expect(stored()).toBe(TOKEN);
    expect(window.location.hash).toBe("");
  });

  it("test_AC_TEN_17_server_failure_offers_retry_with_the_same_token", async () => {
    network.respond = () => problem(503, "organization_busy", "Hay otra operación en curso");
    renderScreen();
    expect(await screen.findByText("Hay otra operación en curso")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: TEXTS.goHome })).not.toBeInTheDocument();
    expect(stored()).toBeNull();

    network.respond = () => json(ACCEPTED);
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText(TEXTS.accepted)).toBeInTheDocument();
    expect(network.requests).toHaveLength(2);
    expect(await network.requests[1]!.json()).toEqual({ token: TOKEN });
    expectNoTokenLeft();
  });

  it("test_AC_TEN_17_network_failure_offers_retry", async () => {
    network.respond = () => {
      throw new TypeError("offline");
    };
    renderScreen();
    expect(await screen.findByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: TEXTS.goHome })).not.toBeInTheDocument();
    expectNoTokenLeft();
  });

  it("test_AC_TEN_17_a_failed_default_save_still_opens_home", async () => {
    saveDefault.mockRejectedValue(new TypeError("offline"));
    renderScreen();
    await userEvent.click(await screen.findByRole("button", { name: TEXTS.goToOrganization }));
    expect(push).toHaveBeenCalledWith(HOME_PATH);
    expect(readTabOrganization()).toBe(ACME_ID);
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER, ORGANIZATION_HEADER } from "@/lib/api-client";

import { HOME_PATH, useActiveOrganization } from "../context/ActiveOrgProvider";
import { MY_INVITATIONS_QUERY_KEY, type MyInvitation } from "../hooks/useMyInvitations";
import { ORGANIZATIONS_QUERY_KEY } from "../hooks/useOrganizations";
import { PENDING_INVITATIONS_TEXTS, PendingInvitationsNotice } from "./PendingInvitationsNotice";
import { activeOrganizationResult } from "./tenancy.test-helpers";

// AC-TEN-39 (UI), Q-121, Q-124, design.md §3.9: the notice talks to a fake BFF through the real
// api-client, so what is checked is what goes on the wire (path, no company header, CSRF) and
// what the screen shows only after the backend answered.
type Respond = (request: Request) => Response | Promise<Response>;
const network = vi.hoisted(() => ({
  respond: (() => new Response(null, { status: 500 })) as Respond,
  requests: [] as Request[],
}));

vi.mock("next/navigation", () => ({ useRouter: vi.fn() }));
vi.mock("../context/ActiveOrgProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../context/ActiveOrgProvider")>()),
  useActiveOrganization: vi.fn(),
}));
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
      onSessionExpired: () => undefined,
      onOrganizationError: () => undefined,
      fetch: async (request: Request) => {
        network.requests.push(request.clone());
        return network.respond(request);
      },
    }),
  };
});

const BETA_INVITATION: MyInvitation = {
  id: "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
  organization: { id: "7b2e1d3f-2c4e-4f60-9bac-1d2e3f4a5b6c", name: "Beta" },
  role: "owner",
  expires_at: "2026-11-27T15:30:00Z",
};
const GAMMA_INVITATION: MyInvitation = {
  id: "4d5e6f7a-8b9c-4dae-9f10-2b3c4d5e6f7a",
  organization: { id: "8c3f2e4a-3d5f-4071-8cbd-2e3f4a5b6c7d", name: "Gamma" },
  role: "viewer",
  expires_at: "2026-11-25T03:00:00Z",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function problem(status: number, code: string, title: string, extra: object = {}): Response {
  return new Response(
    JSON.stringify({ type: "about:blank", title, status, code, request_id: "req-1", ...extra }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

function page(results: MyInvitation[]): Response {
  return json({ count: results.length, next: null, previous: null, results });
}

type Handlers = {
  mine: () => Response;
  accept?: (request: Request) => Response | Promise<Response>;
};

function serve({ mine, accept }: Handlers) {
  network.respond = (request) => {
    const { pathname } = new URL(request.url);
    if (request.method === "GET" && pathname === "/api/invitations/mine/") {
      return mine();
    }
    if (request.method === "POST" && accept && pathname.endsWith("/accept/")) {
      return accept(request);
    }
    return new Response(null, { status: 404 });
  };
}

let queryClient: QueryClient;
const push = vi.fn();
let active: ReturnType<typeof useActiveOrganization>;

function renderNotice() {
  return render(
    <QueryClientProvider client={queryClient}>
      <PendingInvitationsNotice />
    </QueryClientProvider>,
  );
}

const acceptButton = (name: string) =>
  within(screen.getByRole("row", { name: new RegExp(name) })).getByRole("button");

beforeEach(() => {
  network.requests.length = 0;
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  active = activeOrganizationResult(null);
  vi.mocked(useActiveOrganization).mockReturnValue(active);
  vi.mocked(useRouter).mockReturnValue({ push } as unknown as ReturnType<typeof useRouter>);
});

afterEach(() => {
  queryClient.clear();
  push.mockClear();
});

describe("PendingInvitationsNotice (AC-TEN-39, Q-121, Q-124, design.md §3.9)", () => {
  it("test_AC_TEN_39_lists_company_role_and_expiry_without_ids", async () => {
    serve({ mine: () => page([BETA_INVITATION, GAMMA_INVITATION]) });
    const { container } = renderNotice();

    expect(screen.getByRole("status", { name: PENDING_INVITATIONS_TEXTS.loading })).toBeVisible();
    const notice = await screen.findByRole("region", { name: PENDING_INVITATIONS_TEXTS.title });
    const beta = within(notice).getByRole("row", { name: /Beta/ });
    expect(beta).toHaveTextContent("owner");
    // Buenos Aires time (UTC-3), whatever the zone of the browser.
    expect(beta).toHaveTextContent("27/11/2026, 12:30");
    expect(within(notice).getByRole("row", { name: /Gamma/ })).toHaveTextContent("viewer");
    expect(container.innerHTML).not.toContain(BETA_INVITATION.id);

    const [request] = network.requests;
    expect(new URL(request!.url).pathname).toBe("/api/invitations/mine/");
    expect(request!.headers.get(ORGANIZATION_HEADER)).toBeNull();
  });

  it("test_AC_TEN_39_without_invitations_nothing_is_shown", async () => {
    serve({ mine: () => page([]) });
    const { container } = renderNotice();
    await waitFor(() => expect(network.requests).toHaveLength(1));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("test_AC_TEN_39_load_error_shows_title_and_retries", async () => {
    let fail = true;
    serve({
      mine: () =>
        fail
          ? problem(503, "service_unavailable", "Servicio no disponible")
          : page([BETA_INVITATION]),
    });
    renderNotice();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Servicio no disponible");

    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("row", { name: /Beta/ })).toBeInTheDocument();
  });

  it("test_AC_TEN_39_accept_posts_without_company_and_refreshes_organizations", async () => {
    let accepted = false;
    serve({
      mine: () => page(accepted ? [GAMMA_INVITATION] : [BETA_INVITATION, GAMMA_INVITATION]),
      accept: () => {
        accepted = true;
        return json({
          organization: BETA_INVITATION.organization,
          role: "owner",
          membership_id: "5e6f7a8b-9cad-4ebf-a021-3c4d5e6f7a8b",
        });
      },
    });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    renderNotice();
    await screen.findByRole("row", { name: /Beta/ });

    await userEvent.click(acceptButton("Beta"));

    const goTo = await screen.findByRole("button", {
      name: PENDING_INVITATIONS_TEXTS.goToOrganization,
    });
    const post = network.requests.find(({ method }) => method === "POST")!;
    expect(new URL(post.url).pathname).toBe(`/api/invitations/${BETA_INVITATION.id}/accept/`);
    expect(post.headers.get(ORGANIZATION_HEADER)).toBeNull();
    expect(post.headers.get(CSRF_HEADER)).toBe("csrf-test-token");
    expect(await post.text()).toBe("");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ORGANIZATIONS_QUERY_KEY });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: MY_INVITATIONS_QUERY_KEY });
    // The list was read again without Beta, but its row stays to go to the company.
    await waitFor(() =>
      expect(network.requests.filter(({ method }) => method === "GET")).toHaveLength(2),
    );
    expect(screen.getByRole("row", { name: /Beta/ })).toContainElement(goTo);

    await userEvent.click(goTo);
    expect(active.selectOrganization).toHaveBeenCalledExactlyOnceWith(
      BETA_INVITATION.organization.id,
    );
    expect(push).toHaveBeenCalledExactlyOnceWith(HOME_PATH);
  });

  it("test_AC_TEN_39_nothing_is_accepted_until_the_backend_answers", async () => {
    let answer: (response: Response) => void = () => undefined;
    serve({
      mine: () => page([BETA_INVITATION, GAMMA_INVITATION]),
      accept: () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    });
    renderNotice();
    await screen.findByRole("row", { name: /Beta/ });

    await userEvent.click(acceptButton("Beta"));

    // While the accept runs: no "Ir a la empresa", and the other invitation waits.
    await waitFor(() => expect(acceptButton("Beta")).toBeDisabled());
    expect(acceptButton("Gamma")).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: PENDING_INVITATIONS_TEXTS.goToOrganization }),
    ).not.toBeInTheDocument();

    answer(problem(500, "internal_error", "Error interno"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Error interno");
    expect(
      screen.queryByRole("button", { name: PENDING_INVITATIONS_TEXTS.goToOrganization }),
    ).not.toBeInTheDocument();
  });

  it.each([
    [400, "invitation_invalid", "Invitación no válida", { reason: "not_found" }],
    [409, "organization_suspended", "Organización suspendida", {}],
    [409, "already_member", "Ya sos miembro de esta empresa", {}],
  ])(
    "test_AC_TEN_39_refused_accept_%s_%s_shows_only_the_title",
    async (status, code, title, extra) => {
      serve({
        mine: () => page([BETA_INVITATION]),
        accept: () => problem(status, code, title, { ...extra, detail: "detail-sentinel" }),
      });
      renderNotice();
      await screen.findByRole("row", { name: /Beta/ });

      await userEvent.click(acceptButton("Beta"));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(title);
      expect(document.body).not.toHaveTextContent("detail-sentinel");
      // Repeating the same request cannot change a refusal: no "Reintentar".
      expect(within(alert).queryByRole("button")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: PENDING_INVITATIONS_TEXTS.goToOrganization }),
      ).not.toBeInTheDocument();
    },
  );

  it("test_AC_TEN_39_refusal_of_the_only_invitation_keeps_the_error", async () => {
    // It expired meanwhile: the list read again comes back empty, the error must stay.
    let refused = false;
    serve({
      mine: () => page(refused ? [] : [BETA_INVITATION]),
      accept: () => {
        refused = true;
        return problem(400, "invitation_invalid", "Invitación no válida", { reason: "expired" });
      },
    });
    renderNotice();
    await screen.findByRole("row", { name: /Beta/ });

    await userEvent.click(acceptButton("Beta"));

    await waitFor(() =>
      expect(network.requests.filter(({ method }) => method === "GET")).toHaveLength(2),
    );
    await waitFor(() =>
      expect(screen.queryByRole("row", { name: /Beta/ })).not.toBeInTheDocument(),
    );
    const notice = screen.getByRole("region", { name: PENDING_INVITATIONS_TEXTS.title });
    expect(within(notice).getByRole("alert")).toHaveTextContent("Invitación no válida");
    expect(within(notice).queryByRole("table")).not.toBeInTheDocument();
  });

  it("test_AC_TEN_39_server_failure_on_accept_offers_retry", async () => {
    let attempts = 0;
    serve({
      mine: () => page([BETA_INVITATION]),
      accept: () => {
        attempts += 1;
        return attempts === 1
          ? problem(502, "bad_gateway", "Error del servidor")
          : json({
              organization: BETA_INVITATION.organization,
              role: "owner",
              membership_id: "5e6f7a8b-9cad-4ebf-a021-3c4d5e6f7a8b",
            });
      },
    });
    renderNotice();
    await screen.findByRole("row", { name: /Beta/ });
    await userEvent.click(acceptButton("Beta"));

    const alert = await screen.findByRole("alert");
    await userEvent.click(within(alert).getByRole("button", { name: "Reintentar" }));

    expect(
      await screen.findByRole("button", { name: PENDING_INVITATIONS_TEXTS.goToOrganization }),
    ).toBeInTheDocument();
    expect(attempts).toBe(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

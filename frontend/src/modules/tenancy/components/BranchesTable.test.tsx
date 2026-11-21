import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BranchesPage from "@/app/(dashboard)/configuracion/sucursales/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { Branch } from "../hooks/useBranches";
import { BRANCHES_TEXTS } from "./BranchesTable";
import {
  CENTRO,
  currentOrganization,
  listAnswer,
  MANAGE_ACTIONS,
  NORTE,
  problem,
  json,
  READ_ACTIONS,
} from "./branches.test-helpers";
import { ACME, activeOrganizationResult } from "./tenancy.test-helpers";

// Configuración → Sucursales (RF-TEN-06, spec §14, design.md §3.9): the screen talks to a fake BFF
// through the real api-client, so what is checked is what goes on the wire (path, company header,
// filter) and what the screen shows from the backend's answers: the actions come only from
// `allowed_actions`, never from the role.
type Respond = (request: Request) => Response | Promise<Response>;
const network = vi.hoisted(() => ({
  respond: (() => new Response(null, { status: 500 })) as Respond,
  requests: [] as Request[],
}));

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

function backend(branches: readonly Branch[], allowed = MANAGE_ACTIONS): Respond {
  return (request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/organizations/current/") return json(currentOrganization(allowed));
    if (pathname === "/api/branches/") return listAnswer(request, branches);
    return problem(404, "not_found", "No encontrado");
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <BranchesPage />
    </QueryClientProvider>,
  );
}

function branchRequests(): Request[] {
  return network.requests.filter((request) => new URL(request.url).pathname === "/api/branches/");
}

async function rowOf(name: string): Promise<HTMLElement> {
  const cell = await screen.findByRole("cell", { name });
  return cell.closest("tr")!;
}

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
  network.respond = () => new Response(null, { status: 500 });
});

describe("Sucursales (RF-TEN-06, spec §14, design.md §3.9)", () => {
  it("test_RF_TEN_06_lists_active_and_inactive_with_the_company_header", async () => {
    network.respond = backend([CENTRO, NORTE]);
    renderPage();

    expect(screen.getByRole("heading", { level: 1, name: BRANCHES_TEXTS.title })).toBeVisible();
    const centro = await rowOf("Centro");
    expect(centro).toHaveTextContent("C-01");
    expect(centro).toHaveTextContent("Av. Siempreviva 742");
    expect(within(centro).getByText(BRANCHES_TEXTS.active)).toBeVisible();
    const norte = await rowOf("Norte");
    expect(within(norte).getByText(BRANCHES_TEXTS.inactive)).toBeVisible();
    expect(within(norte).getAllByText(BRANCHES_TEXTS.missing)).toHaveLength(2);

    for (const request of network.requests) {
      expect(request.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    }
    const [list] = branchRequests();
    expect(new URL(list!.url).searchParams.has("is_active")).toBe(false);
  });

  it("test_RF_TEN_06_actions_follow_allowed_actions", async () => {
    network.respond = backend([CENTRO, NORTE]);
    renderPage();

    const centro = await rowOf("Centro");
    await waitFor(() =>
      expect(within(centro).getByRole("button", { name: BRANCHES_TEXTS.edit })).toBeVisible(),
    );
    expect(within(centro).getByRole("button", { name: BRANCHES_TEXTS.deactivate })).toBeVisible();
    expect(within(centro).queryByRole("button", { name: BRANCHES_TEXTS.reactivate })).toBeNull();
    const norte = await rowOf("Norte");
    expect(within(norte).getByRole("button", { name: BRANCHES_TEXTS.reactivate })).toBeVisible();
    expect(within(norte).queryByRole("button", { name: BRANCHES_TEXTS.deactivate })).toBeNull();
    expect(screen.getByRole("button", { name: BRANCHES_TEXTS.create })).toBeVisible();
  });

  it("test_RF_TEN_06_read_only_without_management_actions", async () => {
    network.respond = backend([CENTRO, NORTE], READ_ACTIONS);
    renderPage();

    await rowOf("Centro");
    await waitFor(() =>
      expect(
        network.requests.some(
          (request) => new URL(request.url).pathname === "/api/organizations/current/",
        ),
      ).toBe(true),
    );
    expect(screen.queryByRole("button", { name: BRANCHES_TEXTS.create })).toBeNull();
    for (const label of [
      BRANCHES_TEXTS.edit,
      BRANCHES_TEXTS.deactivate,
      BRANCHES_TEXTS.reactivate,
    ]) {
      expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
  });

  it("test_RF_TEN_06_only_one_action_shows_only_that_one", async () => {
    network.respond = backend([CENTRO, NORTE], ["branch.read", "branch.reactivate"]);
    renderPage();

    const norte = await rowOf("Norte");
    await waitFor(() =>
      expect(within(norte).getByRole("button", { name: BRANCHES_TEXTS.reactivate })).toBeVisible(),
    );
    const centro = await rowOf("Centro");
    expect(within(centro).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: BRANCHES_TEXTS.edit })).toBeNull();
  });

  it("test_RF_TEN_06_no_actions_while_allowed_actions_fail", async () => {
    const answer = backend([CENTRO]);
    network.respond = (request) =>
      new URL(request.url).pathname === "/api/organizations/current/"
        ? problem(503, "service_unavailable", "Servicio no disponible")
        : answer(request);
    renderPage();

    expect(await screen.findByText(BRANCHES_TEXTS.actionsUnknown)).toBeVisible();
    const centro = await rowOf("Centro");
    expect(within(centro).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: BRANCHES_TEXTS.create })).toBeNull();

    network.respond = answer;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() =>
      expect(within(centro).getByRole("button", { name: BRANCHES_TEXTS.edit })).toBeVisible(),
    );
  });

  it("test_RF_TEN_06_filter_asks_the_backend_for_active_or_inactive", async () => {
    network.respond = backend([CENTRO, NORTE]);
    renderPage();
    await rowOf("Norte");

    await userEvent.click(screen.getByRole("button", { name: BRANCHES_TEXTS.filters.active }));
    await waitFor(() => expect(screen.queryByRole("cell", { name: "Norte" })).toBeNull());
    expect(await screen.findByRole("cell", { name: "Centro" })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: BRANCHES_TEXTS.filters.inactive }));
    expect(await screen.findByRole("cell", { name: "Norte" })).toBeVisible();
    expect(screen.queryByRole("cell", { name: "Centro" })).toBeNull();

    const filters = branchRequests().map((request) =>
      new URL(request.url).searchParams.get("is_active"),
    );
    expect(filters).toEqual([null, "true", "false"]);
  });

  it("test_RF_TEN_06_empty_states_per_filter_and_role", async () => {
    network.respond = backend([]);
    renderPage();

    const empty = await screen.findByRole("region", { name: BRANCHES_TEXTS.emptyCanCreate });
    expect(within(empty).getByRole("button", { name: BRANCHES_TEXTS.create })).toBeVisible();
    // A table is never shown empty.
    expect(screen.queryByRole("table")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: BRANCHES_TEXTS.filters.inactive }));
    expect(await screen.findByRole("region", { name: BRANCHES_TEXTS.emptyInactive })).toBeVisible();
  });

  it("test_RF_TEN_06_empty_read_only", async () => {
    network.respond = backend([], READ_ACTIONS);
    renderPage();

    const empty = await screen.findByRole("region", { name: BRANCHES_TEXTS.emptyReadOnly });
    expect(within(empty).queryByRole("button")).toBeNull();
  });

  it("test_RF_TEN_06_loading_shows_skeleton_rows", async () => {
    network.respond = () => new Promise<Response>(() => undefined);
    renderPage();

    const status = screen.getByRole("status", { name: BRANCHES_TEXTS.loading });
    expect(status.querySelectorAll('[data-skeleton="row"]')).toHaveLength(5);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("test_RF_TEN_06_forbidden_shows_no_permission", async () => {
    const answer = backend([CENTRO]);
    network.respond = (request) =>
      new URL(request.url).pathname === "/api/branches/"
        ? problem(403, "forbidden", "No tenés permiso")
        : answer(request);
    renderPage();

    expect(await screen.findByRole("region", { name: BRANCHES_TEXTS.forbidden })).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("test_RF_TEN_06_error_retries_the_same_request", async () => {
    const answer = backend([CENTRO]);
    network.respond = (request) =>
      new URL(request.url).pathname === "/api/branches/"
        ? problem(500, "internal_error", "Error interno")
        : answer(request);
    renderPage();

    expect(await screen.findByText("Error interno")).toBeVisible();
    network.respond = answer;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("cell", { name: "Centro" })).toBeVisible();
  });

  it("test_RF_TEN_06_no_request_without_a_company", () => {
    vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(null));
    renderPage();

    expect(screen.getByRole("status", { name: BRANCHES_TEXTS.loading })).toBeVisible();
    expect(network.requests).toHaveLength(0);
  });

  it("test_Q_220_keeps_the_place_of_the_cash_registers", () => {
    network.respond = backend([CENTRO]);
    renderPage();

    expect(screen.getByRole("region", { name: BRANCHES_TEXTS.registersTitle })).toHaveTextContent(
      BRANCHES_TEXTS.registersText,
    );
  });
});

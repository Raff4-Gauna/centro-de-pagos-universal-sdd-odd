import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER, ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { Branch } from "../hooks/useBranches";
import { BRANCH_FORM_ERRORS } from "../lib/branch-form";
import { BRANCH_FORM_TEXTS } from "./BranchFormDialog";
import { BRANCH_STATUS_TEXTS } from "./BranchStatusDialog";
import { BRANCHES_TEXTS, BranchesScreen } from "./BranchesTable";
import {
  CENTRO,
  currentOrganization,
  json,
  listAnswer,
  MANAGE_ACTIONS,
  NORTE,
  problem,
} from "./branches.test-helpers";
import { ACME, activeOrganizationResult, BETA } from "./tenancy.test-helpers";

// The writes of "Sucursales" (RF-TEN-06, AC-TEN-30, AC-TEN-38 in the UI, design.md §3.9): create,
// edit, deactivate and reactivate against a fake BFF through the real api-client. A dialog closes
// and the list changes only after the backend's `2xx`; a refusal stays in the dialog.
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

// A fake backend that keeps the branches; `write` answers the writes (default: as the backend).
function backend(initial: Branch[], write?: (request: Request) => Response | undefined): Respond {
  let branches = [...initial];
  return async (request) => {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/organizations/current/")
      return json(currentOrganization(MANAGE_ACTIONS));
    if (request.method === "GET" && pathname === "/api/branches/")
      return listAnswer(request, branches);
    const answer = write?.(request);
    if (answer) return answer;
    if (request.method === "POST" && pathname === "/api/branches/") {
      const body = (await request.json()) as Pick<Branch, "name" | "code" | "address">;
      const created = {
        id: "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
        is_active: true,
        deactivated_at: null,
        ...body,
      };
      branches = [...branches, created];
      return json(created, 201);
    }
    const [, , , id, transition] = pathname.split("/");
    const branch = branches.find((candidate) => candidate.id === id);
    if (!branch) return problem(404, "not_found", "No encontrado");
    const changed: Branch =
      request.method === "PATCH"
        ? { ...branch, ...((await request.json()) as Partial<Branch>) }
        : { ...branch, is_active: transition === "reactivate" };
    branches = branches.map((candidate) => (candidate.id === id ? changed : candidate));
    return json(changed);
  };
}

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <BranchesScreen />
    </QueryClientProvider>,
  );
  return {
    rerender: () =>
      view.rerender(
        <QueryClientProvider client={queryClient}>
          <BranchesScreen />
        </QueryClientProvider>,
      ),
  };
}

function writes(): Request[] {
  return network.requests.filter((request) => request.method !== "GET");
}

async function openCreate() {
  await userEvent.click(await screen.findByRole("button", { name: BRANCHES_TEXTS.create }));
  return screen.getByRole("dialog", { name: BRANCH_FORM_TEXTS.createTitle });
}

async function rowButton(name: string, label: string) {
  const row = (await screen.findByRole("cell", { name })).closest("tr")!;
  return within(row).findByRole("button", { name: label });
}

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
  network.respond = () => new Response(null, { status: 500 });
});

describe("BranchFormDialog (RF-TEN-06, design.md §3.9, §6)", () => {
  it("test_RF_TEN_06_create_sends_trimmed_values_and_shows_after_201", async () => {
    network.respond = backend([CENTRO]);
    renderScreen();
    const dialog = await openCreate();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "  Sur  ");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Código/ }), "S-1");
    await userEvent.click(within(dialog).getByRole("button", { name: BRANCH_FORM_TEXTS.create }));

    expect(await screen.findByRole("cell", { name: "Sur" })).toBeVisible();
    expect(screen.queryByRole("dialog")).toBeNull();
    const [post] = writes();
    expect(new URL(post!.url).pathname).toBe("/api/branches/");
    expect(post!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    expect(post!.headers.get(CSRF_HEADER)).toBe("csrf-test-token");
    expect(await post!.json()).toEqual({ name: "Sur", code: "S-1", address: "" });
  });

  it("test_RF_TEN_06_name_is_required_before_sending", async () => {
    network.respond = backend([CENTRO]);
    renderScreen();
    const dialog = await openCreate();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "   ");
    await userEvent.click(within(dialog).getByRole("button", { name: BRANCH_FORM_TEXTS.create }));

    expect(within(dialog).getByText(BRANCH_FORM_ERRORS.nameRequired)).toBeVisible();
    expect(writes()).toHaveLength(0);
  });

  it("test_AC_TEN_38_conflict_stays_in_the_form_with_its_detail", async () => {
    const detail = "Ya hay una sucursal activa con ese nombre.";
    network.respond = backend([CENTRO], (request) =>
      request.method === "POST" ? problem(409, "conflict", "Conflicto", { detail }) : undefined,
    );
    renderScreen();
    const dialog = await openCreate();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "centro");
    await userEvent.click(within(dialog).getByRole("button", { name: BRANCH_FORM_TEXTS.create }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(detail);
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(screen.queryByRole("cell", { name: "centro" })).toBeNull();
  });

  it("test_RF_TEN_06_validation_error_goes_under_its_field", async () => {
    network.respond = backend([CENTRO], (request) =>
      request.method === "POST"
        ? problem(400, "validation_error", "Datos inválidos", {
            errors: [{ field: "code", code: "max_length", message: "Como máximo 32 caracteres." }],
          })
        : undefined,
    );
    renderScreen();
    const dialog = await openCreate();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Sur");
    await userEvent.click(within(dialog).getByRole("button", { name: BRANCH_FORM_TEXTS.create }));

    const code = within(dialog).getByRole("textbox", { name: /Código/ });
    await waitFor(() => expect(code).toHaveAccessibleDescription("Como máximo 32 caracteres."));
    expect(within(dialog).queryByRole("alert")).toBeNull();
  });

  it("test_RF_TEN_06_edit_sends_only_what_changed", async () => {
    network.respond = backend([CENTRO]);
    renderScreen();
    await userEvent.click(await rowButton("Centro", BRANCHES_TEXTS.edit));
    const dialog = screen.getByRole("dialog", { name: BRANCH_FORM_TEXTS.editTitle });
    const address = within(dialog).getByRole("textbox", { name: /Dirección/ });
    expect(within(dialog).getByRole("textbox", { name: /Nombre/ })).toHaveValue("Centro");

    await userEvent.clear(address);
    await userEvent.type(address, "Calle Falsa 123");
    await userEvent.click(within(dialog).getByRole("button", { name: BRANCH_FORM_TEXTS.save }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [patch] = writes();
    expect(patch!.method).toBe("PATCH");
    expect(new URL(patch!.url).pathname).toBe(`/api/branches/${CENTRO.id}/`);
    expect(await patch!.json()).toEqual({ address: "Calle Falsa 123" });
    expect(await screen.findByText("Calle Falsa 123")).toBeVisible();
  });

  it("test_RF_TEN_06_edit_without_changes_sends_nothing", async () => {
    network.respond = backend([CENTRO]);
    renderScreen();
    await userEvent.click(await rowButton("Centro", BRANCHES_TEXTS.edit));
    const dialog = screen.getByRole("dialog", { name: BRANCH_FORM_TEXTS.editTitle });

    await userEvent.click(within(dialog).getByRole("button", { name: BRANCH_FORM_TEXTS.save }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(writes()).toHaveLength(0);
  });

  it("test_RF_TEN_06_dialog_closes_when_the_tab_changes_company", async () => {
    network.respond = backend([CENTRO]);
    const { rerender } = renderScreen();
    await openCreate();

    vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(BETA.id));
    rerender();

    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("BranchStatusDialog (RN-TEN-19, AC-TEN-30, design.md §3.9)", () => {
  it("test_RF_TEN_06_deactivate_after_confirmation_and_200", async () => {
    network.respond = backend([CENTRO]);
    renderScreen();
    await userEvent.click(await rowButton("Centro", BRANCHES_TEXTS.deactivate));
    const dialog = screen.getByRole("dialog", {
      name: BRANCH_STATUS_TEXTS.deactivate.title("Centro"),
    });
    expect(writes()).toHaveLength(0);

    await userEvent.click(
      within(dialog).getByRole("button", { name: BRANCH_STATUS_TEXTS.deactivate.confirm }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [post] = writes();
    expect(new URL(post!.url).pathname).toBe(`/api/branches/${CENTRO.id}/deactivate/`);
    expect(post!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    const row = (await screen.findByRole("cell", { name: "Centro" })).closest("tr")!;
    expect(await within(row).findByText(BRANCHES_TEXTS.inactive)).toBeVisible();
  });

  it("test_AC_TEN_30_reactivate_with_taken_name_stays_inactive", async () => {
    const message = "Ya hay una sucursal activa con ese nombre.";
    network.respond = backend([NORTE], (request) =>
      request.method === "POST"
        ? problem(400, "validation_error", "Datos inválidos", {
            errors: [{ field: "name", code: "taken", message }],
          })
        : undefined,
    );
    renderScreen();
    await userEvent.click(await rowButton("Norte", BRANCHES_TEXTS.reactivate));
    const dialog = screen.getByRole("dialog", {
      name: BRANCH_STATUS_TEXTS.reactivate.title("Norte"),
    });

    await userEvent.click(
      within(dialog).getByRole("button", { name: BRANCH_STATUS_TEXTS.reactivate.confirm }),
    );

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
    // The list sits behind the modal (hidden from the accessibility tree while it is open).
    const row = screen.getByRole("cell", { name: "Norte", hidden: true }).closest("tr")!;
    expect(within(row).getByText(BRANCHES_TEXTS.inactive)).toBeVisible();
  });

  it("test_AC_TEN_37_invalid_transition_shows_its_title_and_rereads", async () => {
    network.respond = backend([CENTRO], (request) =>
      request.method === "POST"
        ? problem(409, "invalid_transition", "Transición inválida")
        : undefined,
    );
    renderScreen();
    await userEvent.click(await rowButton("Centro", BRANCHES_TEXTS.deactivate));
    const listsBefore = network.requests.filter((request) => request.method === "GET").length;

    await userEvent.click(
      screen.getByRole("button", { name: BRANCH_STATUS_TEXTS.deactivate.confirm }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Transición inválida");
    await waitFor(() =>
      expect(network.requests.filter((request) => request.method === "GET").length).toBeGreaterThan(
        listsBefore,
      ),
    );
  });
});

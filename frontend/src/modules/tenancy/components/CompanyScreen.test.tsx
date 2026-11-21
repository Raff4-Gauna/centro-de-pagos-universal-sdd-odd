import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CompanyPage from "@/app/(dashboard)/configuracion/empresa/page";
import { ORGANIZATION_HEADER } from "@/lib/api-client";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import type { CurrentOrganizationDetails } from "../hooks/useCurrentOrganizationDetails";
import { COMPANY_FORM_ERRORS } from "../lib/company-form";
import { currentOrganization, json, problem } from "./branches.test-helpers";
import { COMPANY_FORM_TEXTS } from "./CompanyDataForm";
import { COMPANY_TEXTS } from "./CompanyScreen";
import { ACME, activeOrganizationResult, BETA } from "./tenancy.test-helpers";

// "Datos de la empresa" (RF-TEN-03, spec §14, design.md §3.9) against a fake BFF through the real
// api-client: read-only without `org.update`, the zod check before sending, the backend's `400`
// under its field, and nothing shown saved before the `2xx`.
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

const EDITOR: CurrentOrganizationDetails = {
  ...currentOrganization(["org.read", "org.update", "member.leave"]),
  legal_name: "Acme S.A.",
  tax_id: "30712345671",
};
const READER: CurrentOrganizationDetails = {
  ...currentOrganization(["org.read", "member.leave"]),
  my_role: "viewer",
};

// A fake backend that keeps one company per id; `patch` answers the `PATCH` (default: apply it).
function backend(
  companies: Record<string, CurrentOrganizationDetails>,
  patch?: (request: Request) => Response | undefined,
): Respond {
  return async (request) => {
    const id = request.headers.get(ORGANIZATION_HEADER) ?? "";
    const company = companies[id];
    if (new URL(request.url).pathname !== "/api/organizations/current/" || !company) {
      return problem(404, "organization_not_found", "Organización no encontrada");
    }
    if (request.method === "PATCH") {
      const answer = patch?.(request);
      if (answer) return answer;
      companies[id] = { ...company, ...((await request.json()) as object) };
    }
    return json(companies[id]);
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <CompanyPage />
    </QueryClientProvider>,
  );
  return {
    rerender: () =>
      view.rerender(
        <QueryClientProvider client={queryClient}>
          <CompanyPage />
        </QueryClientProvider>,
      ),
  };
}

function patches(): Request[] {
  return network.requests.filter((request) => request.method === "PATCH");
}

function field(label: string) {
  return screen.getByRole("textbox", { name: label });
}

beforeEach(() => {
  vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
});

afterEach(() => {
  network.requests.length = 0;
});

describe("Datos de la empresa (RF-TEN-03, spec §14, design.md §3.9)", () => {
  it("test_RF_TEN_03_read_only_without_org_update", async () => {
    network.respond = backend({ [ACME.id]: READER });
    renderPage();
    expect(screen.getByRole("status", { name: COMPANY_TEXTS.loading })).toBeVisible();
    expect(await screen.findByText("Acme")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: COMPANY_TEXTS.title })).toBeVisible();
    // Not informed: "—", never an empty value.
    expect(screen.getAllByText(COMPANY_TEXTS.missing)).toHaveLength(2);
    expect(screen.getByText("America/Argentina/Buenos_Aires")).toBeVisible();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: COMPANY_FORM_TEXTS.save })).toBeNull();
    // Leaving does not depend on editing.
    expect(screen.getByRole("button", { name: COMPANY_TEXTS.leave })).toBeVisible();
  });

  it("test_RF_TEN_03_no_actions_while_loading_or_without_member_leave", async () => {
    network.respond = backend({ [ACME.id]: currentOrganization(["org.read"]) });
    renderPage();
    expect(screen.queryByRole("button", { name: COMPANY_TEXTS.leave })).toBeNull();
    expect(await screen.findByText("Acme")).toBeVisible();
    expect(screen.queryByRole("button", { name: COMPANY_TEXTS.leave })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("test_RF_TEN_03_error_retries", async () => {
    let fail = true;
    const company = backend({ [ACME.id]: EDITOR });
    network.respond = (request) =>
      fail ? problem(500, "internal_error", "Error interno del servidor") : company(request);
    renderPage();
    expect(await screen.findByText("Error interno del servidor")).toBeVisible();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByDisplayValue("Acme")).toBeVisible();
  });

  it("test_RF_TEN_03_403_is_no_permission", async () => {
    network.respond = () => problem(403, "forbidden", "Sin permiso");
    renderPage();
    expect(await screen.findByRole("heading", { name: COMPANY_TEXTS.forbidden })).toBeVisible();
  });

  it("test_RF_TEN_03_timezone_is_shown_not_edited_until_Q_240", async () => {
    network.respond = backend({ [ACME.id]: EDITOR });
    renderPage();
    const zone = await screen.findByDisplayValue("America/Argentina/Buenos_Aires");
    expect(zone).toHaveAttribute("readonly");
    expect(zone).toHaveAccessibleDescription(COMPANY_FORM_TEXTS.timezoneHelp);
  });

  it("test_RF_TEN_03_zod_errors_block_the_request", async () => {
    network.respond = backend({ [ACME.id]: EDITOR });
    renderPage();
    const name = await screen.findByDisplayValue("Acme");
    await userEvent.clear(name);
    await userEvent.type(name, "   ");
    await userEvent.clear(field(COMPANY_FORM_TEXTS.labels.tax_id));
    await userEvent.type(field(COMPANY_FORM_TEXTS.labels.tax_id), "123");
    await userEvent.click(screen.getByRole("button", { name: COMPANY_FORM_TEXTS.save }));

    expect(await screen.findByText(COMPANY_FORM_ERRORS.nameRequired)).toBeVisible();
    expect(screen.getByText(COMPANY_FORM_ERRORS.taxIdInvalid)).toBeVisible();
    expect(patches()).toHaveLength(0);
  });

  it("test_RF_TEN_03_save_sends_only_the_changes_to_the_company_shown", async () => {
    network.respond = backend({ [ACME.id]: { ...EDITOR } });
    renderPage();
    const legal = await screen.findByDisplayValue("Acme S.A.");
    await userEvent.clear(legal);
    await userEvent.type(legal, "  Acme Argentina S.A. ");
    const tax = field(COMPANY_FORM_TEXTS.labels.tax_id);
    await userEvent.clear(tax);
    await userEvent.type(tax, "30-71234567-1");
    await userEvent.click(screen.getByRole("button", { name: COMPANY_FORM_TEXTS.save }));

    expect(await screen.findByText(COMPANY_FORM_TEXTS.saved)).toBeVisible();
    const [sent] = patches();
    expect(patches()).toHaveLength(1);
    expect(sent!.headers.get(ORGANIZATION_HEADER)).toBe(ACME.id);
    // The same CUIT with hyphens is no change, so it does not travel.
    expect(await sent!.json()).toEqual({ legal_name: "Acme Argentina S.A." });
    // The form now holds the backend's answer: nothing left to save.
    expect(screen.getByDisplayValue("Acme Argentina S.A.")).toBeVisible();
    expect(screen.getByRole("button", { name: COMPANY_FORM_TEXTS.save })).toBeDisabled();
  });

  it("test_RF_TEN_03_backend_400_goes_under_its_field", async () => {
    network.respond = backend({ [ACME.id]: EDITOR }, () =>
      problem(400, "validation_error", "Datos inválidos", {
        errors: [{ field: "tax_id", code: "invalid", message: "No es un CUIT válido." }],
      }),
    );
    renderPage();
    const tax = await screen.findByDisplayValue("30712345671");
    await userEvent.clear(tax);
    await userEvent.type(tax, "30712345672");
    await userEvent.click(screen.getByRole("button", { name: COMPANY_FORM_TEXTS.save }));

    await waitFor(() =>
      expect(field(COMPANY_FORM_TEXTS.labels.tax_id)).toHaveAccessibleDescription(
        "No es un CUIT válido.",
      ),
    );
    expect(screen.queryByText("Datos inválidos")).toBeNull();
    expect(screen.queryByText(COMPANY_FORM_TEXTS.saved)).toBeNull();
    expect(tax).toHaveValue("30712345672");
  });

  it("test_RF_TEN_03_busy_and_suspended_show_their_title", async () => {
    let answer = problem(503, "organization_busy", "Hay otra operación en curso, probá de nuevo");
    const companies = { [ACME.id]: { ...EDITOR } };
    network.respond = backend(companies, () => answer);
    renderPage();
    const name = await screen.findByDisplayValue("Acme");
    await userEvent.type(name, " 2");
    await userEvent.click(screen.getByRole("button", { name: COMPANY_FORM_TEXTS.save }));
    expect(await screen.findByText("Hay otra operación en curso, probá de nuevo")).toBeVisible();
    expect(name).toHaveValue("Acme 2");

    // Suspended meanwhile: the company is read again and the form gives way to the view.
    answer = problem(409, "organization_suspended", "La organización está suspendida");
    companies[ACME.id] = { ...EDITOR, status: "suspended", allowed_actions: ["org.read"] };
    await userEvent.click(screen.getByRole("button", { name: COMPANY_FORM_TEXTS.save }));
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(screen.getByText("Acme")).toBeVisible();
  });

  it("test_RF_TEN_03_switching_company_discards_the_form", async () => {
    network.respond = backend({
      [ACME.id]: EDITOR,
      [BETA.id]: { ...EDITOR, id: BETA.id, name: "Beta" },
    });
    const view = renderPage();
    const name = await screen.findByDisplayValue("Acme");
    await userEvent.type(name, " sin guardar");

    vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(BETA.id));
    view.rerender();
    expect(await screen.findByDisplayValue("Beta")).toBeVisible();
    expect(screen.queryByDisplayValue(/sin guardar/)).toBeNull();

    vi.mocked(useActiveOrganization).mockReturnValue(activeOrganizationResult(ACME.id));
    view.rerender();
    expect(await screen.findByDisplayValue("Acme")).toBeVisible();
    expect(patches()).toHaveLength(0);
  });
});

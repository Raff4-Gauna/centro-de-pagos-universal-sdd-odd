import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RETRY_LABEL } from "@/components/ErrorNotice";
import { ApiError } from "@/lib/problem";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import { useOrganizations } from "../hooks/useOrganizations";
import {
  ALL_BRANCHES_LABEL,
  BRANCH_LABEL,
  ORGANIZATION_LABEL,
  OrgBranchSelector,
  SELECTOR_GROUP_LABEL,
  SUSPENDED_CHIP_LABEL,
} from "./OrgBranchSelector";
import { ACME, activeOrganizationResult, BETA, organizationsResult } from "./tenancy.test-helpers";

vi.mock("../hooks/useOrganizations", () => ({ useOrganizations: vi.fn() }));
vi.mock("../context/ActiveOrgProvider", () => ({ useActiveOrganization: vi.fn() }));

const organizations = vi.mocked(useOrganizations);
const activeOrganization = vi.mocked(useActiveOrganization);

const group = () => screen.getByRole("group", { name: SELECTOR_GROUP_LABEL });

describe("OrgBranchSelector (RF-TEN-02, spec §14, 07 §5.1, design.md §3.9)", () => {
  beforeEach(() => {
    organizations.mockReturnValue(organizationsResult({ data: [ACME, BETA] }));
    activeOrganization.mockReturnValue(activeOrganizationResult(ACME.id));
  });

  it("test_RF_TEN_02_selector_shows_the_active_company_and_all_branches", () => {
    render(<OrgBranchSelector />);
    const company = within(group()).getByRole("combobox", { name: ORGANIZATION_LABEL });
    expect(company).toHaveTextContent(ACME.name);
    const branch = within(group()).getByRole("combobox", { name: BRANCH_LABEL });
    expect(branch).toHaveTextContent(ALL_BRANCHES_LABEL);
    expect(branch).toHaveAttribute("aria-disabled", "true");
    expect(group()).toHaveAttribute("aria-busy", "false");
  });

  it("test_RF_TEN_02_selector_lists_companies_and_marks_suspended", async () => {
    const result = activeOrganizationResult(ACME.id);
    activeOrganization.mockReturnValue(result);
    render(<OrgBranchSelector />);

    await userEvent.click(within(group()).getByRole("combobox", { name: ORGANIZATION_LABEL }));
    const options = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      ACME.name,
      `${BETA.name}${SUSPENDED_CHIP_LABEL}`,
    ]);
    await userEvent.click(options[1]!);

    expect(result.selectOrganization).toHaveBeenCalledExactlyOnceWith(BETA.id);
  });

  it("test_RF_TEN_02_selector_shows_the_suspended_chip_on_the_active_company", () => {
    activeOrganization.mockReturnValue(activeOrganizationResult(BETA.id));
    render(<OrgBranchSelector />);
    const company = within(group()).getByRole("combobox", { name: ORGANIZATION_LABEL });
    expect(company).toHaveTextContent(`${BETA.name}${SUSPENDED_CHIP_LABEL}`);
  });

  it("test_RF_TEN_02_selector_loading_shows_skeletons", () => {
    organizations.mockReturnValue(organizationsResult({ isPending: true }));
    activeOrganization.mockReturnValue(activeOrganizationResult(null));
    render(<OrgBranchSelector />);
    expect(group()).toHaveAttribute("aria-busy", "true");
    expect(within(group()).queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("test_RF_TEN_02_selector_error_offers_retry", async () => {
    const error = new ApiError({
      status: 503,
      code: "service_unavailable",
      title: "Servicio no disponible",
      requestId: "r",
    });
    const result = organizationsResult({ isError: true, error });
    organizations.mockReturnValue(result);
    activeOrganization.mockReturnValue(activeOrganizationResult(null));
    render(<OrgBranchSelector />);

    expect(within(group()).getByRole("alert")).toHaveTextContent(error.title);
    await userEvent.click(within(group()).getByRole("button", { name: RETRY_LABEL }));
    expect(result.refetch).toHaveBeenCalledTimes(1);
  });

  it("test_RF_TEN_02_selector_without_companies_is_disabled_and_empty", () => {
    organizations.mockReturnValue(organizationsResult({ data: [] }));
    activeOrganization.mockReturnValue(activeOrganizationResult(null));
    render(<OrgBranchSelector />);
    const company = within(group()).getByRole("combobox", { name: ORGANIZATION_LABEL });
    expect(company).toHaveAttribute("aria-disabled", "true");
    expect(company.textContent?.replace("​", "").trim()).toBe("");
  });
});

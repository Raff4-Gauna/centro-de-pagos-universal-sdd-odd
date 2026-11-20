import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useCurrentOrganization } from "../hooks/useCurrentOrganization";
import { SUSPENDED_TEXT, SuspendedBanner } from "./SuspendedBanner";
import { ACME, BETA } from "./tenancy.test-helpers";

vi.mock("../hooks/useCurrentOrganization", () => ({ useCurrentOrganization: vi.fn() }));

const current = vi.mocked(useCurrentOrganization);

describe("SuspendedBanner (spec §14, Q-208, design.md §3.9)", () => {
  it("test_RF_TEN_02_suspended_company_shows_read_only_banner", () => {
    current.mockReturnValue({ organization: BETA, isSuspended: true });
    render(<SuspendedBanner />);
    expect(screen.getByRole("alert")).toHaveTextContent(SUSPENDED_TEXT);
    expect(SUSPENDED_TEXT).toBe("Organización suspendida (solo lectura)");
  });

  it("test_RF_TEN_02_active_or_missing_company_shows_no_banner", () => {
    current.mockReturnValue({ organization: ACME, isSuspended: false });
    const { rerender } = render(<SuspendedBanner />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    current.mockReturnValue({ organization: null, isSuspended: false });
    rerender(<SuspendedBanner />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

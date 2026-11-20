import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLogout } from "../hooks/useLogout";
import { CSRF_REFUSED, logoutResult } from "./identity.test-helpers";
import {
  NO_ORGANIZATION_TITLE,
  NoOrganizationState,
  OPERATOR_CONTACT_LABEL,
} from "./NoOrganizationState";
import { LOGOUT_LABEL } from "./UserMenu";

vi.mock("../hooks/useLogout", () => ({ useLogout: vi.fn() }));

const logout = vi.mocked(useLogout);

describe("NoOrganizationState (AC-IDA-30, Q-109, spec §14, design.md §3.4)", () => {
  beforeEach(() => {
    logout.mockReturnValue(logoutResult());
  });

  it("test_AC_IDA_30_no_organization_state_shows_text_and_logout", async () => {
    const result = logoutResult();
    logout.mockReturnValue(result);
    render(<NoOrganizationState />);
    expect(NO_ORGANIZATION_TITLE).toBe("No pertenecés a ninguna empresa");
    expect(screen.getByRole("heading", { name: NO_ORGANIZATION_TITLE })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: LOGOUT_LABEL }));
    expect(result.mutate).toHaveBeenCalledTimes(1);
  });

  it("test_Q_205_operator_contact_and_invitations_are_shown_when_given", () => {
    const { rerender } = render(
      <NoOrganizationState operatorContact="soporte@example.com">
        <p>invitaciones</p>
      </NoOrganizationState>,
    );
    expect(screen.getByText(`${OPERATOR_CONTACT_LABEL}: soporte@example.com`)).toBeInTheDocument();
    expect(screen.getByText("invitaciones")).toBeInTheDocument();

    rerender(<NoOrganizationState operatorContact={null} />);
    expect(screen.queryByText(new RegExp(OPERATOR_CONTACT_LABEL))).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: NO_ORGANIZATION_TITLE })).toBeInTheDocument();
  });

  it("test_AC_IDA_30_logout_in_progress_blocks_a_second_click", () => {
    logout.mockReturnValue(logoutResult({ isPending: true }));
    render(<NoOrganizationState />);
    expect(screen.getByRole("button", { name: LOGOUT_LABEL })).toBeDisabled();
  });

  it("test_AC_IDA_30_logout_refused_shows_error_with_retry", async () => {
    const result = logoutResult({ isError: true, error: CSRF_REFUSED });
    logout.mockReturnValue(result);
    render(<NoOrganizationState />);
    // The session is still open: the state stays, with the error and a retry (07 §2).
    expect(screen.getByRole("heading", { name: NO_ORGANIZATION_TITLE })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(CSRF_REFUSED.title);
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(result.mutate).toHaveBeenCalledTimes(1);
  });
});

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLogout } from "@/modules/identity/hooks/useLogout";
import { logoutResult } from "@/modules/identity/components/identity.test-helpers";
import {
  NO_ORGANIZATION_TITLE,
  OPERATOR_CONTACT_LABEL,
} from "@/modules/identity/components/NoOrganizationState";

import NoOrganizationPage from "./page";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));
vi.mock("next/server", () => ({ connection: vi.fn(async () => undefined) }));
vi.mock("@/modules/identity/hooks/useLogout", () => ({ useLogout: vi.fn() }));
// The notice has its own tests (PendingInvitationsNotice.test.tsx); here only that it is mounted.
vi.mock("@/modules/tenancy/components/PendingInvitationsNotice", () => ({
  PendingInvitationsNotice: () => <p>pending-invitations-notice</p>,
}));

async function renderPage() {
  render(await NoOrganizationPage());
}

beforeEach(() => {
  vi.mocked(useLogout).mockReturnValue(logoutResult());
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("/sin-organizacion (AC-IDA-30, Q-109, Q-205, Q-124, SPEC-02 design.md §3.9)", () => {
  it("test_AC_IDA_30_no_organization_page_mounts_the_state_and_the_invitations", async () => {
    vi.stubEnv("OPERATOR_CONTACT", "soporte@example.com");
    await renderPage();
    expect(screen.getByRole("heading", { name: NO_ORGANIZATION_TITLE })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar sesión" })).toBeInTheDocument();
    expect(screen.getByText(`${OPERATOR_CONTACT_LABEL}: soporte@example.com`)).toBeInTheDocument();
    expect(screen.getByText("pending-invitations-notice")).toBeInTheDocument();
  });

  it("test_Q_205_without_operator_contact_the_page_shows_none", async () => {
    vi.stubEnv("OPERATOR_CONTACT", "");
    await renderPage();
    expect(screen.getByRole("heading", { name: NO_ORGANIZATION_TITLE })).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(OPERATOR_CONTACT_LABEL))).not.toBeInTheDocument();
  });
});

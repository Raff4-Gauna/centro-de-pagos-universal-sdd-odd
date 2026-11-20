import { render, screen } from "@testing-library/react";
import { headers } from "next/headers";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InvitationPage from "./page";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ headers: vi.fn() }));
// The screen has its own tests (AcceptInvitation.test.tsx); here only what the page hands it.
vi.mock("@/modules/tenancy/components/AcceptInvitation", () => ({
  AcceptInvitation: ({ hasSession }: { hasSession: boolean }) => (
    <p>{`accept-invitation session=${String(hasSession)}`}</p>
  ),
}));

const RT = "__Host-cpu_rt";

function withCookie(cookie?: string) {
  const values = new Headers(cookie === undefined ? {} : { cookie });
  vi.mocked(headers).mockResolvedValue(values as Awaited<ReturnType<typeof headers>>);
}

async function renderPage() {
  render(await InvitationPage());
}

beforeEach(() => {
  vi.mocked(headers).mockReset();
});

describe("/invitacion (AC-TEN-17, design.md §3.9)", () => {
  it("test_AC_TEN_17_page_with_session_cookie_tells_the_screen", async () => {
    withCookie(`${RT}=opaque-refresh`);
    await renderPage();
    expect(screen.getByText("accept-invitation session=true")).toBeInTheDocument();
  });

  it.each([undefined, "__Host-cpu_at=jwt", `${RT}=a; ${RT}=b`])(
    "test_AC_TEN_17_page_without_exactly_one_session_cookie_has_no_session (%s)",
    async (cookie) => {
      withCookie(cookie);
      await renderPage();
      expect(screen.getByText("accept-invitation session=false")).toBeInTheDocument();
    },
  );
});

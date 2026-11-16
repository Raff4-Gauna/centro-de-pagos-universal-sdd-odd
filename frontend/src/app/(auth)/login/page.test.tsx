import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const APP = "https://app.example";
const START = "/api/auth/google/start";

type Params = Record<string, string | string[] | undefined>;

async function renderPage(params: Params) {
  render(await LoginPage({ searchParams: Promise.resolve(params) }));
}

function startHref(): string | null {
  return screen.getByRole("link", { name: "Ingresar con Google" }).getAttribute("href");
}

beforeEach(() => {
  vi.stubEnv("HUB_APP_ORIGIN", APP);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Ingresar (AC-IDA-19, design.md §3.4)", () => {
  it("test_AC_IDA_19_internal_return_to_is_kept_for_start", async () => {
    await renderPage({ return_to: "/cobros?estado=pendiente" });
    expect(startHref()).toBe(`${START}?return_to=%2Fcobros%3Festado%3Dpendiente`);
  });

  it.each(["//evil.example", "https://evil.example/x", "/\\evil.example", "/\t/evil.example"])(
    "test_AC_IDA_19_hostile_return_to_%j_becomes_inicio",
    async (hostile) => {
      await renderPage({ return_to: hostile });
      expect(startHref()).toBe(`${START}?return_to=%2F`);
    },
  );

  it.each(["/..//evil.example", "/.//evil.example"])(
    "test_AC_IDA_19_dot_segments_in_%j_never_leave_the_app",
    async (hostile) => {
      await renderPage({ return_to: hostile });
      const back = new URL(startHref()!, APP).searchParams.get("return_to")!;
      expect(back.startsWith("//")).toBe(false);
      expect(new URL(back, APP).origin).toBe(APP);
    },
  );

  it("test_AC_IDA_19_without_return_to_start_has_no_return_to", async () => {
    await renderPage({});
    expect(startHref()).toBe(START);
  });

  it("test_AC_IDA_19_repeated_return_to_is_not_picked_from", async () => {
    await renderPage({ return_to: ["/cobros", "//evil.example"] });
    expect(startHref()).toBe(START);
  });

  it("test_AC_IDA_19_without_app_origin_start_has_no_return_to", async () => {
    vi.stubEnv("HUB_APP_ORIGIN", "");
    await renderPage({ return_to: "/cobros" });
    expect(startHref()).toBe(START);
  });

  it("test_AC_IDA_19_unknown_error_shows_the_generic_text_not_the_value", async () => {
    await renderPage({ error: "<b>detalle secreto</b>" });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("No pudimos completar el ingreso. Probá de nuevo");
    expect(document.body).not.toHaveTextContent("detalle secreto");
  });

  it("test_AC_IDA_19_known_error_shows_its_text", async () => {
    await renderPage({ error: "not_invited", return_to: "/cobros" });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Pedile a un administrador de tu empresa que te invite",
    );
  });

  it("test_AC_IDA_19_without_error_no_alert_is_shown", async () => {
    await renderPage({ return_to: "/cobros" });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

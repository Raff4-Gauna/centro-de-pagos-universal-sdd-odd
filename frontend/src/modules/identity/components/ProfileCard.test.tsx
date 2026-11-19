import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProfilePage from "@/app/(dashboard)/configuracion/perfil/page";
import { ApiError } from "@/lib/problem";

import { useMe } from "../hooks/useMe";
import { ME, meResult } from "./identity.test-helpers";
import { initialsOf, PROFILE_NOTE, PROFILE_TITLE } from "./ProfileCard";

vi.mock("../hooks/useMe", () => ({ useMe: vi.fn() }));

const me = vi.mocked(useMe);

describe("Mi perfil (RF-IDA-06, spec §14, Q-115, design.md §3.4)", () => {
  beforeEach(() => {
    me.mockReturnValue(meResult({ data: ME }));
  });

  it("test_RF_IDA_06_profile_shows_name_email_and_note_read_only", () => {
    render(<ProfilePage />);
    expect(screen.getByRole("heading", { level: 1, name: PROFILE_TITLE })).toBeInTheDocument();
    expect(PROFILE_TITLE).toBe("Mi perfil");
    expect(screen.getAllByText(ME.display_name).length).toBeGreaterThan(0);
    expect(screen.getByText(ME.email)).toBeInTheDocument();
    expect(PROFILE_NOTE).toBe("Los datos vienen de tu cuenta de Google");
    expect(screen.getByText(PROFILE_NOTE)).toBeInTheDocument();
    // Read only and without language (Q-115): nothing to edit.
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/idioma/i)).toBeNull();
  });

  it("test_RF_IDA_06_profile_without_avatar_shows_initials", () => {
    me.mockReturnValue(meResult({ data: { ...ME, avatar_url: null } }));
    render(<ProfilePage />);
    expect(screen.getByText("AP")).toBeInTheDocument();
    expect(initialsOf("Ana", "ana@example.com")).toBe("A");
    expect(initialsOf("ana maría pérez", "x@example.com")).toBe("AM");
    expect(initialsOf("  ", "zoe@example.com")).toBe("Z");
  });

  it("test_RF_IDA_06_profile_ignores_a_non_https_avatar", () => {
    me.mockReturnValue(meResult({ data: { ...ME, avatar_url: "http://example.com/a.png" } }));
    const { container } = render(<ProfilePage />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("AP")).toBeInTheDocument();
  });

  it("test_RF_IDA_06_profile_loading_shows_detail_skeleton", () => {
    me.mockReturnValue(meResult({ isPending: true }));
    render(<ProfilePage />);
    const status = screen.getByRole("status", { name: "Cargando" });
    expect(status).toHaveAttribute("data-variant", "detail");
  });

  it("test_RF_IDA_06_profile_error_shows_retry", async () => {
    const result = meResult({
      isError: true,
      error: new ApiError({
        status: 0,
        code: "client.network_error",
        title: "No se pudo conectar con el servidor",
        requestId: null,
      }),
    });
    me.mockReturnValue(result);
    render(<ProfilePage />);
    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo conectar con el servidor");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(result.refetch).toHaveBeenCalledTimes(1);
  });
});

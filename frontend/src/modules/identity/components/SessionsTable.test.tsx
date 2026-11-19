import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SecurityPage from "@/app/(dashboard)/configuracion/seguridad/page";
import { ApiError } from "@/lib/problem";

import { useLogout } from "../hooks/useLogout";
import { useRevokeOtherSessions } from "../hooks/useRevokeOtherSessions";
import { useRevokeSession } from "../hooks/useRevokeSession";
import { type Session, useSessions } from "../hooks/useSessions";
import { logoutResult } from "./identity.test-helpers";
import { REVOKE_OTHERS_TEXTS } from "./RevokeOthersDialog";
import { REVOKE_CURRENT_TEXTS, REVOKE_OTHER_TEXTS } from "./RevokeSessionDialog";
import { SECURITY_TEXTS, SESSIONS_SKELETON_ROWS } from "./SessionsTable";

vi.mock("../hooks/useSessions", () => ({ useSessions: vi.fn() }));
vi.mock("../hooks/useRevokeSession", () => ({ useRevokeSession: vi.fn() }));
vi.mock("../hooks/useRevokeOtherSessions", () => ({ useRevokeOtherSessions: vi.fn() }));
vi.mock("../hooks/useLogout", () => ({ useLogout: vi.fn() }));

const CURRENT: Session = {
  id: "11111111-1111-4111-8111-111111111111",
  browser: "Chrome",
  os: "Windows",
  created_at: "2026-11-19T12:00:00Z",
  last_used_at: "2026-11-19T15:30:00Z",
  is_current: true,
};
const OTHER: Session = {
  id: "22222222-2222-4222-8222-222222222222",
  browser: "Safari",
  os: "iOS",
  created_at: "2026-11-10T13:00:00Z",
  last_used_at: "2026-11-18T20:15:00Z",
  is_current: false,
};

type QueryState = Partial<{
  data: Session[];
  isPending: boolean;
  isError: boolean;
  isFetching: boolean;
  error: ApiError | null;
}>;

function sessionsResult(state: QueryState) {
  return {
    data: undefined,
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...state,
  } as unknown as ReturnType<typeof useSessions>;
}

type MutationState = Partial<{ isPending: boolean; isError: boolean; error: ApiError | null }>;
type MutateOptions<T> = { onSuccess?: (value: T) => void };

// `mutate` runs the `onSuccess` the screen passes, as TanStack Query does after a 2xx; with
// `isError` set it does nothing, as a failed mutation.
function mutationResult<T>(state: MutationState = {}, outcome?: T) {
  return {
    mutate: vi.fn((_variables?: unknown, options?: MutateOptions<T>) => {
      if (!state.isError) options?.onSuccess?.(outcome as T);
    }),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...state,
  };
}

const sessions = vi.mocked(useSessions);
const revoke = vi.mocked(useRevokeSession);
const revokeOthers = vi.mocked(useRevokeOtherSessions);
const logout = vi.mocked(useLogout);

let revokeMock: ReturnType<typeof mutationResult<string>>;
let othersMock: ReturnType<typeof mutationResult<void>>;
let logoutMock: ReturnType<typeof logoutResult>;

function useRevoke(mock: ReturnType<typeof mutationResult<string>>) {
  revokeMock = mock;
  revoke.mockReturnValue(mock as unknown as ReturnType<typeof useRevokeSession>);
}

function rowOf(text: string): HTMLElement {
  return screen.getByText(text).closest("tr")!;
}

async function openRowAction(device: string, label: string) {
  await userEvent.click(within(rowOf(device)).getByRole("button", { name: label }));
  return screen.getByRole("dialog");
}

describe("Seguridad (AC-IDA-33, RF-IDA-07, Q-113, Q-129, design.md §3.4)", () => {
  beforeEach(() => {
    sessions.mockReturnValue(sessionsResult({ data: [CURRENT, OTHER] }));
    useRevoke(mutationResult<string>({}, "revoked"));
    othersMock = mutationResult<void>();
    revokeOthers.mockReturnValue(
      othersMock as unknown as ReturnType<typeof useRevokeOtherSessions>,
    );
    logoutMock = logoutResult();
    logout.mockReturnValue(logoutMock);
  });

  it("test_AC_IDA_33_lists_device_and_dates_without_ip", () => {
    const { container } = render(<SecurityPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Seguridad" })).toBeInTheDocument();
    const headers = screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(headers).toEqual(["Dispositivo", "Iniciada", "Último uso", "Acciones"]);
    const current = rowOf("Chrome · Windows");
    expect(current).toHaveTextContent("19/11/2026, 09:00");
    expect(current).toHaveTextContent("19/11/2026, 12:30");
    expect(within(current).getByText("Esta sesión")).toBeInTheDocument();
    const other = rowOf("Safari · iOS");
    expect(other).toHaveTextContent("10/11/2026, 10:00");
    expect(other).toHaveTextContent("18/11/2026, 17:15");
    expect(within(other).queryByText("Esta sesión")).toBeNull();
    // No IP and no session id on the screen; no password (spec §14).
    expect(container.textContent).not.toMatch(/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/);
    expect(container.innerHTML).not.toContain(OTHER.id);
    expect(container.innerHTML).not.toContain(CURRENT.id);
    expect(screen.queryByText(/contraseña/i)).toBeNull();
  });

  it("test_AC_IDA_33_unknown_browser_and_os_have_their_text", () => {
    sessions.mockReturnValue(sessionsResult({ data: [{ ...CURRENT, browser: null, os: " " }] }));
    render(<SecurityPage />);
    expect(screen.getByText("Navegador desconocido · Sistema desconocido")).toBeInTheDocument();
  });

  it("test_AC_IDA_33_revoke_others_is_disabled_without_other_sessions", () => {
    sessions.mockReturnValue(sessionsResult({ data: [CURRENT] }));
    render(<SecurityPage />);
    expect(screen.getByRole("button", { name: "Cerrar las demás" })).toBeDisabled();
  });

  it("test_AC_IDA_33_revoke_others_confirms_then_posts", async () => {
    render(<SecurityPage />);
    await userEvent.click(screen.getByRole("button", { name: "Cerrar las demás" }));
    const dialog = screen.getByRole("dialog", { name: REVOKE_OTHERS_TEXTS.title });
    expect(REVOKE_OTHERS_TEXTS.title).toBe("¿Cerrar las demás sesiones?");
    expect(dialog).toHaveTextContent(
      "Los otros dispositivos van a tener que ingresar de nuevo con Google. Esta sesión sigue abierta.",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar las demás" }));
    expect(othersMock.mutate).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    // No success message (Q-129): the list refreshes by itself.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("test_AC_IDA_33_cancel_closes_without_revoking", async () => {
    render(<SecurityPage />);
    await userEvent.click(screen.getByRole("button", { name: "Cerrar las demás" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(othersMock.mutate).not.toHaveBeenCalled();
    await openRowAction("Safari · iOS", "Cerrar sesión");
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(revokeMock.mutate).not.toHaveBeenCalled();
  });

  it("test_AC_IDA_33_other_session_confirms_then_revokes_by_id", async () => {
    render(<SecurityPage />);
    const dialog = await openRowAction("Safari · iOS", "Cerrar sesión");
    expect(dialog).toHaveAccessibleName("¿Cerrar la sesión de Safari · iOS?");
    expect(REVOKE_OTHER_TEXTS.body).toBe(
      "Ese dispositivo va a tener que ingresar de nuevo con Google.",
    );
    expect(dialog).toHaveTextContent(REVOKE_OTHER_TEXTS.body);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar sesión" }));
    expect(revokeMock.mutate).toHaveBeenCalledWith(OTHER.id, expect.anything());
    expect(logoutMock.mutate).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("test_AC_IDA_33_already_ended_session_closes_without_error", async () => {
    useRevoke(mutationResult<string>({}, "already_ended"));
    render(<SecurityPage />);
    const dialog = await openRowAction("Safari · iOS", "Cerrar sesión");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar sesión" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("test_AC_IDA_33_current_session_confirms_and_uses_the_bff_logout", async () => {
    render(<SecurityPage />);
    const dialog = await openRowAction("Chrome · Windows", "Cerrar esta sesión");
    expect(dialog).toHaveAccessibleName(REVOKE_CURRENT_TEXTS.title);
    expect(REVOKE_CURRENT_TEXTS.title).toBe("¿Cerrar esta sesión?");
    expect(dialog).toHaveTextContent("Vas a volver a la pantalla de ingreso.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar esta sesión" }));
    expect(logoutMock.mutate).toHaveBeenCalledTimes(1);
    // Never its own revoke endpoint: only the BFF logout clears the cookies (design.md §3.4).
    expect(revokeMock.mutate).not.toHaveBeenCalled();
  });

  it("test_AC_IDA_33_current_session_stays_blocked_while_leaving", async () => {
    logout.mockReturnValue(logoutResult({ isSuccess: true }));
    render(<SecurityPage />);
    const dialog = await openRowAction("Chrome · Windows", "Cerrar esta sesión");
    expect(within(dialog).getByRole("button", { name: /Cerrar esta sesión/ })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Cancelar" })).toBeDisabled();
  });

  it("test_AC_IDA_33_failed_logout_keeps_the_dialog_with_the_fixed_title", async () => {
    logout.mockReturnValue(
      logoutResult({
        isError: true,
        error: new ApiError({
          status: 403,
          code: "bff.csrf_failed",
          title: "Solicitud rechazada",
          requestId: "req-1",
        }),
      }),
    );
    render(<SecurityPage />);
    const dialog = await openRowAction("Chrome · Windows", "Cerrar esta sesión");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Solicitud rechazada");
  });

  it("test_AC_IDA_33_failed_revoke_shows_the_fixed_title_in_the_dialog", async () => {
    const failure = new ApiError({
      status: 500,
      code: "internal_error",
      title: "Error interno",
      detail: "raw detail",
      requestId: "req-1",
    });
    useRevoke(mutationResult<string>({ isError: true, error: failure }));
    render(<SecurityPage />);
    const dialog = await openRowAction("Safari · iOS", "Cerrar sesión");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cerrar sesión" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Error interno");
    expect(dialog).not.toHaveTextContent("raw detail");
  });

  it("test_AC_IDA_33_loading_shows_a_table_skeleton_of_five_rows", () => {
    sessions.mockReturnValue(sessionsResult({ isPending: true }));
    const { container } = render(<SecurityPage />);
    expect(screen.getByRole("status", { name: "Cargando" })).toBeInTheDocument();
    expect(SESSIONS_SKELETON_ROWS).toBe(5);
    expect(container.querySelectorAll('[data-skeleton="row"]')).toHaveLength(5);
  });

  it("test_AC_IDA_33_load_error_offers_retry", async () => {
    const result = sessionsResult({
      isError: true,
      error: new ApiError({
        status: 0,
        code: "client.network_error",
        title: "No se pudo conectar con el servidor",
        requestId: null,
      }),
    });
    sessions.mockReturnValue(result);
    render(<SecurityPage />);
    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo conectar con el servidor");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(result.refetch).toHaveBeenCalledTimes(1);
  });

  it("test_AC_IDA_33_empty_list_shows_the_empty_state", () => {
    sessions.mockReturnValue(sessionsResult({ data: [] }));
    render(<SecurityPage />);
    expect(SECURITY_TEXTS.empty).toBe("No hay sesiones activas");
    expect(screen.getByRole("heading", { name: "No hay sesiones activas" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

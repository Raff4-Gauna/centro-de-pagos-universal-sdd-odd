import { vi } from "vitest";

import { ApiError } from "@/lib/problem";

import type { useLogout } from "../hooks/useLogout";
import type { Me, useMe } from "../hooks/useMe";

// Shapes of the two hooks for the component tests, which mock them: only the fields read.
export const ME: Me = {
  id: "0b6f8a52-4a8e-4f61-9d0c-6d3b8f0e2a11",
  email: "ana@example.com",
  display_name: "Ana Pérez",
  avatar_url: "https://lh3.googleusercontent.com/a/avatar",
  memberships: [],
};

export const CSRF_REFUSED = new ApiError({
  status: 403,
  code: "bff.csrf_failed",
  title: "Solicitud rechazada",
  requestId: "req-1",
});

type MeState = Partial<{
  data: Me;
  isPending: boolean;
  isError: boolean;
  isFetching: boolean;
  error: ApiError | null;
}>;

export function meResult(state: MeState) {
  return {
    data: undefined,
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...state,
  } as unknown as ReturnType<typeof useMe>;
}

type LogoutState = Partial<{
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  error: ApiError | null;
}>;

export function logoutResult(state: LogoutState = {}) {
  return {
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    error: null,
    ...state,
  } as unknown as ReturnType<typeof useLogout>;
}

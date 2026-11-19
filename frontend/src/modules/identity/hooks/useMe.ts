"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient, type ApiClient } from "@/lib/api-client";
import { apiErrorFromResponse, type ApiError } from "@/lib/problem";
import type { components } from "@/types/api";

// The signed-in person (RF-IDA-06, design.md §6.2): identity and active memberships, read through
// the typed client, so a `401` the BFF could not refresh sends the browser to "Ingresar". One
// query shared by the user menu, "Mi perfil" and whoever needs the memberships.
export type Me = components["schemas"]["Me"];

export const ME_QUERY_KEY = ["me"] as const;

export async function fetchMe(client: ApiClient = apiClient, signal?: AbortSignal): Promise<Me> {
  const { data, response } = await client.GET("/api/me/", { signal });
  if (data === undefined) {
    // A 2xx without the body of the contract: an unexpected response, never an empty person.
    throw await apiErrorFromResponse(response);
  }
  return data;
}

export function useMe() {
  return useQuery<Me, ApiError>({
    queryKey: ME_QUERY_KEY,
    queryFn: ({ signal }) => fetchMe(apiClient, signal),
  });
}

"use client";

import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { AppRouterCacheProvider } from "@mui/material-nextjs/v16-appRouter";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { getQueryClient } from "@/lib/query-client";
import { theme } from "@/lib/theme";

// Client providers of the whole app (design.md §3.3.1): the Emotion cache that streams MUI styles
// with the App Router, the theme built from the design tokens, MUI's reset and the React Query cache.
export function Providers({ children }: Readonly<{ children: ReactNode }>) {
  const queryClient = getQueryClient();
  return (
    <AppRouterCacheProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </ThemeProvider>
    </AppRouterCacheProvider>
  );
}

"use client";

import Toolbar from "@mui/material/Toolbar";
import { type ReactNode, useCallback, useState } from "react";

import { NavMenu } from "./NavMenu";
import { TopBar } from "./TopBar";

// Shell of every (dashboard) route (07 §5, design.md §3.3.2): top bar + navigation + page content.
// Its only state is whether the mobile drawer is open; there is no data nor route protection yet.
export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const openNav = useCallback(() => setMobileOpen(true), []);
  const closeNav = useCallback(() => setMobileOpen(false), []);

  return (
    <div className="tw-flex tw-min-h-screen">
      <TopBar onOpenNav={openNav} />
      <NavMenu mobileOpen={mobileOpen} onCloseMobile={closeNav} />
      <main className="tw-min-w-0 tw-grow tw-p-4 md:tw-p-6">
        <Toolbar />
        {children}
      </main>
    </div>
  );
}

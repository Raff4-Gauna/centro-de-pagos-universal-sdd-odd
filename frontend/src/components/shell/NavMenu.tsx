"use client";

import HomeOutlined from "@mui/icons-material/HomeOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Toolbar from "@mui/material/Toolbar";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// Main navigation of the (dashboard) shell (design.md §3.3.2, spec §14): only Inicio and
// Configuración exist in 00-platform; each module adds its own entry when it ships.
export const NAV_WIDTH = 240;
export const NAV_LABEL = "Navegación principal";

type NavItem = Readonly<{ href: string; label: string; icon: ReactNode }>;

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/inicio", label: "Inicio", icon: <HomeOutlined /> },
  { href: "/configuracion", label: "Configuración", icon: <SettingsOutlined /> },
];

// An item is active on its own route and on any route below it (`/configuracion/...`).
export function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavList({ onNavigate }: Readonly<{ onNavigate?: () => void }>) {
  const pathname = usePathname();
  return (
    <nav aria-label={NAV_LABEL}>
      <List>
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <ListItemButton
              key={item.href}
              component={Link}
              href={item.href}
              selected={active}
              aria-current={active ? "page" : undefined}
              onClick={onNavigate}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          );
        })}
      </List>
    </nav>
  );
}

export type NavMenuProps = Readonly<{ mobileOpen: boolean; onCloseMobile: () => void }>;

const PAPER = { sx: { width: NAV_WIDTH, boxSizing: "border-box" } } as const;

// Permanent drawer from `md` up; temporary drawer (opened from the top bar) below it. The
// temporary one is not kept mounted, so a closed mobile menu leaves a single nav in the page.
export function NavMenu({ mobileOpen, onCloseMobile }: NavMenuProps) {
  return (
    <>
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onCloseMobile}
        sx={{ display: { md: "none" } }}
        slotProps={{ paper: PAPER }}
      >
        <NavList onNavigate={onCloseMobile} />
      </Drawer>
      <Drawer
        variant="permanent"
        open
        sx={{ display: { xs: "none", md: "block" }, width: NAV_WIDTH, flexShrink: 0 }}
        slotProps={{ paper: PAPER }}
      >
        <Toolbar />
        <NavList />
      </Drawer>
    </>
  );
}

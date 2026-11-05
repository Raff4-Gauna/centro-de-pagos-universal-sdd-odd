import MenuIcon from "@mui/icons-material/Menu";
import AppBar from "@mui/material/AppBar";
import IconButton from "@mui/material/IconButton";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

import { OrgBranchSelectorPlaceholder } from "./OrgBranchSelectorPlaceholder";
import { UserMenuPlaceholder } from "./UserMenuPlaceholder";

// Top bar of the (dashboard) shell (design.md §3.3.2): menu button (only below `md`, where the
// navigation is a temporary drawer), app title, the company/branch selector and the user menu.
// Responsive `display` of MUI components goes through `sx`, not a `tw-` class: ButtonBase sets its
// own `display` and the two would fight on specificity (07 §1).
export const APP_TITLE = "Centro de Pagos Universal";
export const OPEN_NAV_LABEL = "Abrir navegación";

export type TopBarProps = Readonly<{ onOpenNav: () => void }>;

export function TopBar({ onOpenNav }: TopBarProps) {
  return (
    <AppBar
      position="fixed"
      color="inherit"
      elevation={0}
      sx={{ zIndex: (theme) => theme.zIndex.drawer + 1, borderBottom: 1, borderColor: "divider" }}
    >
      <Toolbar className="tw-gap-2">
        <IconButton
          edge="start"
          aria-label={OPEN_NAV_LABEL}
          onClick={onOpenNav}
          sx={{ display: { md: "none" } }}
        >
          <MenuIcon />
        </IconButton>
        <Typography component="div" variant="h6" noWrap className="tw-hidden sm:tw-block">
          {APP_TITLE}
        </Typography>
        <div className="tw-ml-auto tw-flex tw-items-center tw-gap-2">
          <OrgBranchSelectorPlaceholder />
          <UserMenuPlaceholder />
        </div>
      </Toolbar>
    </AppBar>
  );
}

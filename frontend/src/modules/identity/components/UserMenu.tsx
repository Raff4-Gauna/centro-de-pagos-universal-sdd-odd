"use client";

import AccountCircleOutlined from "@mui/icons-material/AccountCircleOutlined";
import LogoutOutlined from "@mui/icons-material/LogoutOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import { useState, type MouseEvent } from "react";

import { RETRY_LABEL } from "@/components/ErrorNotice";
import type { ApiError } from "@/lib/problem";

import { useLogout } from "../hooks/useLogout";
import { useMe } from "../hooks/useMe";
import { UserAvatar } from "./ProfileCard";

// User menu of the shell (spec §14, design.md §3.4): who is signed in and "Cerrar sesión", which
// does not depend on `GET /api/me` (loading or failed, the menu still logs out). A refused logout
// left the session open (T-IDA-25): the menu says so, with the fixed title of the error's code,
// and offers a retry; it never navigates away as if the session were closed.
export const USER_MENU_LABEL = "Menú de usuario";
export const LOGOUT_LABEL = "Cerrar sesión";
const MENU_ID = "user-menu";

export function LogoutErrorAlert({
  error,
  onRetry,
  retrying,
}: Readonly<{ error: ApiError; onRetry: () => void; retrying: boolean }>) {
  return (
    <Alert
      severity="error"
      action={
        <Button color="inherit" size="small" onClick={onRetry} loading={retrying}>
          {RETRY_LABEL}
        </Button>
      }
    >
      {error.title}
    </Alert>
  );
}

export function UserMenu() {
  const me = useMe();
  const logout = useLogout();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = anchor !== null;
  // After the `204` the browser is leaving for "Ingresar": the action stays blocked until then.
  const leaving = logout.isPending || logout.isSuccess;

  return (
    <>
      <IconButton
        edge="end"
        aria-label={USER_MENU_LABEL}
        aria-haspopup="menu"
        aria-controls={open ? MENU_ID : undefined}
        aria-expanded={open}
        onClick={(event: MouseEvent<HTMLElement>) => setAnchor(event.currentTarget)}
      >
        {me.data ? <UserAvatar me={me.data} size={32} /> : <AccountCircleOutlined />}
      </IconButton>
      <Menu id={MENU_ID} anchorEl={anchor} open={open} onClose={() => setAnchor(null)}>
        {me.data ? (
          <li className="tw-px-4 tw-pb-2 tw-pt-1">
            <Typography variant="subtitle2" noWrap>
              {me.data.display_name.trim() || me.data.email}
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {me.data.email}
            </Typography>
          </li>
        ) : null}
        <MenuItem disabled={leaving} onClick={() => logout.mutate()}>
          <ListItemIcon>
            {leaving ? <CircularProgress size={20} /> : <LogoutOutlined fontSize="small" />}
          </ListItemIcon>
          <ListItemText>{LOGOUT_LABEL}</ListItemText>
        </MenuItem>
      </Menu>
      <Snackbar
        open={logout.isError}
        onClose={(_event, reason) => {
          if (reason !== "clickaway") logout.reset();
        }}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <div>
          {logout.error ? (
            <LogoutErrorAlert
              error={logout.error}
              onRetry={() => logout.mutate()}
              retrying={logout.isPending}
            />
          ) : null}
        </div>
      </Snackbar>
    </>
  );
}

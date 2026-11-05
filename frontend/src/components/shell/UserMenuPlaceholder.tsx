import AccountCircleOutlined from "@mui/icons-material/AccountCircleOutlined";
import IconButton from "@mui/material/IconButton";

// Place of the user menu (07 §5, spec §14): disabled and empty until SPEC-01 brings login and
// sessions. It shows no name nor avatar because there is no user yet.
export const USER_MENU_LABEL = "Menú de usuario (disponible con SPEC-01)";

export function UserMenuPlaceholder() {
  return (
    <IconButton disabled aria-label={USER_MENU_LABEL} edge="end">
      <AccountCircleOutlined />
    </IconButton>
  );
}

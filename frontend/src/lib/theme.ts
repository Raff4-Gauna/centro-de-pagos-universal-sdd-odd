import { createTheme } from "@mui/material/styles";

import { breakpoints, colors, radius, spacingUnit, typography } from "./design-tokens";

// MUI theme built only from lib/design-tokens.ts (07 §1, RF-PLT-15). Imported by the client
// providers: a theme is not serializable, so it never crosses the server/client boundary as a prop.
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { ...colors.primary },
    secondary: { ...colors.secondary },
    error: { ...colors.error },
    warning: { ...colors.warning },
    info: { ...colors.info },
    success: { ...colors.success },
    background: { ...colors.background },
    text: { ...colors.text },
    divider: colors.divider,
  },
  shape: { borderRadius: radius.md },
  spacing: spacingUnit,
  breakpoints: { values: { ...breakpoints } },
  typography: {
    fontFamily: typography.fontFamily,
    fontSize: typography.fontSize,
    fontWeightRegular: typography.fontWeightRegular,
    fontWeightMedium: typography.fontWeightMedium,
    fontWeightBold: typography.fontWeightBold,
    button: { textTransform: "none", fontWeight: typography.fontWeightMedium },
  },
});

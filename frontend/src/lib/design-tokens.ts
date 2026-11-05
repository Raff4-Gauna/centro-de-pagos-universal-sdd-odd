// Single source of the visual tokens (07 §1, design.md §3.3.1, RF-PLT-15): the MUI theme
// (lib/theme.ts) and tailwind.config.ts both read from here, so a brand change is made in one place.
// Provisional neutral palette: the Hub has no brand yet.

export const colors = {
  primary: { main: "#37474f", light: "#62727b", dark: "#102027", contrastText: "#ffffff" },
  secondary: { main: "#546e7a", light: "#819ca9", dark: "#29434e", contrastText: "#ffffff" },
  error: { main: "#c62828", light: "#ef5350", dark: "#8e0000", contrastText: "#ffffff" },
  warning: { main: "#b26a00", light: "#ffa726", dark: "#7a4500", contrastText: "#ffffff" },
  info: { main: "#1565c0", light: "#5e92f3", dark: "#003c8f", contrastText: "#ffffff" },
  success: { main: "#2e7d32", light: "#60ad5e", dark: "#005005", contrastText: "#ffffff" },
  background: { default: "#f5f6f7", paper: "#ffffff" },
  text: { primary: "#1f2328", secondary: "#5c636a", disabled: "#9aa0a6" },
  divider: "#dde1e4",
} as const;

// Corner radius in px. `md` is the default of MUI components (theme.shape.borderRadius).
export const radius = { sm: 4, md: 8, lg: 12 } as const;

// System font stack: nothing is downloaded at build or run time.
export const typography = {
  fontFamily:
    '"Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
  fontSize: 14,
  fontWeightRegular: 400,
  fontWeightMedium: 500,
  fontWeightBold: 600,
} as const;

// MUI `theme.spacing(1)` in px. Tailwind keeps its default 4 px scale, so `tw-p-2` = spacing(1).
export const spacingUnit = 8;

// Breakpoints (min width, px) shared by MUI and Tailwind `screens`: `md:` means the same in both.
export const breakpoints = { xs: 0, sm: 600, md: 900, lg: 1200, xl: 1536 } as const;

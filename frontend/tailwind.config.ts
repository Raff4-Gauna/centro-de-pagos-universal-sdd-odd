import type { Config } from "tailwindcss";

import { breakpoints, colors, radius, typography } from "./src/lib/design-tokens";

// Tailwind 3.4 only for layout and spacing around MUI components (07 §1, D-07). `tw-` prefix so its
// classes never read like MUI ones; no preflight because MUI's CssBaseline is the only reset.
const px = (value: number): string => `${value}px`;

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  prefix: "tw-",
  corePlugins: { preflight: false },
  theme: {
    screens: {
      sm: px(breakpoints.sm),
      md: px(breakpoints.md),
      lg: px(breakpoints.lg),
      xl: px(breakpoints.xl),
    },
    extend: {
      colors: {
        primary: {
          DEFAULT: colors.primary.main,
          light: colors.primary.light,
          dark: colors.primary.dark,
        },
        secondary: {
          DEFAULT: colors.secondary.main,
          light: colors.secondary.light,
          dark: colors.secondary.dark,
        },
        error: colors.error.main,
        warning: colors.warning.main,
        info: colors.info.main,
        success: colors.success.main,
        surface: colors.background.paper,
        canvas: colors.background.default,
        divider: colors.divider,
        "text-primary": colors.text.primary,
        "text-secondary": colors.text.secondary,
      },
      borderRadius: {
        sm: px(radius.sm),
        DEFAULT: px(radius.md),
        md: px(radius.md),
        lg: px(radius.lg),
      },
      fontFamily: { sans: [typography.fontFamily] },
    },
  },
  plugins: [],
};

export default config;

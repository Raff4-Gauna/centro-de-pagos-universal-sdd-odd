import { describe, expect, it } from "vitest";

import tailwindConfig from "../../tailwind.config";
import { breakpoints, colors, radius, spacingUnit, typography } from "./design-tokens";
import { theme } from "./theme";

describe("visual base from one tokens file (RF-PLT-15, 07 §1)", () => {
  it("test_RF_PLT_15_theme_built_from_design_tokens", () => {
    expect(theme.palette.primary.main).toBe(colors.primary.main);
    expect(theme.palette.secondary.main).toBe(colors.secondary.main);
    expect(theme.palette.error.main).toBe(colors.error.main);
    expect(theme.palette.background.default).toBe(colors.background.default);
    expect(theme.palette.text.primary).toBe(colors.text.primary);
    expect(theme.palette.divider).toBe(colors.divider);
    expect(theme.shape.borderRadius).toBe(radius.md);
    expect(theme.spacing(1)).toBe(`${spacingUnit}px`);
    expect(theme.breakpoints.values).toEqual(breakpoints);
    expect(theme.typography.fontFamily).toBe(typography.fontFamily);
    expect(theme.typography.button.textTransform).toBe("none");
  });

  it("test_RF_PLT_15_tailwind_reads_the_same_tokens_with_prefix_and_no_preflight", () => {
    expect(tailwindConfig.prefix).toBe("tw-");
    expect(tailwindConfig.corePlugins).toEqual({ preflight: false });
    const extend = tailwindConfig.theme?.extend;
    expect(extend?.colors).toMatchObject({
      primary: { DEFAULT: colors.primary.main },
      divider: colors.divider,
    });
    expect(extend?.borderRadius).toMatchObject({ DEFAULT: `${radius.md}px` });
    // Same breakpoints as MUI, so `md:tw-…` and `theme.breakpoints.up("md")` switch together.
    expect(tailwindConfig.theme?.screens).toEqual({
      sm: `${breakpoints.sm}px`,
      md: `${breakpoints.md}px`,
      lg: `${breakpoints.lg}px`,
      xl: `${breakpoints.xl}px`,
    });
  });
});

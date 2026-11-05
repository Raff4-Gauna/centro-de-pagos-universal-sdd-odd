import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DETAIL_SKELETON_FIELDS,
  FORM_SKELETON_FIELDS,
  PageSkeleton,
  type PageSkeletonVariant,
  TABLE_SKELETON_ROWS,
} from "./PageSkeleton";

function count(container: HTMLElement, part: string): number {
  return container.querySelectorAll(`[data-skeleton="${part}"]`).length;
}

const EXPECTED: Record<PageSkeletonVariant, [string, number]> = {
  table: ["row", TABLE_SKELETON_ROWS],
  form: ["field", FORM_SKELETON_FIELDS],
  detail: ["field", DETAIL_SKELETON_FIELDS],
};

describe("PageSkeleton (RF-PLT-15, 07 §2)", () => {
  it("test_RF_PLT_15_page_skeleton_variants", () => {
    for (const variant of Object.keys(EXPECTED) as PageSkeletonVariant[]) {
      const [part, parts] = EXPECTED[variant];
      const { container, unmount } = render(<PageSkeleton variant={variant} />);
      const status = screen.getByRole("status", { name: "Cargando" });
      expect(status).toHaveAttribute("aria-busy", "true");
      expect(status).toHaveAttribute("data-variant", variant);
      expect(count(container, "title")).toBe(1);
      expect(count(container, part)).toBe(parts);
      unmount();
    }
  });

  it("test_RF_PLT_15_table_skeleton_has_5_to_8_ghost_rows_and_a_header", () => {
    const { container } = render(<PageSkeleton variant="table" />);
    expect(count(container, "header")).toBe(1);
    expect(TABLE_SKELETON_ROWS).toBeGreaterThanOrEqual(5);
    expect(TABLE_SKELETON_ROWS).toBeLessThanOrEqual(8);
  });

  it("test_RF_PLT_15_form_skeleton_ends_with_an_action", () => {
    const { container } = render(<PageSkeleton variant="form" />);
    expect(count(container, "action")).toBe(1);
  });
});

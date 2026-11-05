import Button from "@mui/material/Button";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

describe("EmptyState (AC-PLT-28, 07 §2)", () => {
  it("test_AC_PLT_28_empty_state_renders_title_and_text", () => {
    render(<EmptyState title="Todavía no hay cobros" description="Cuando cobres, aparecen acá." />);
    const region = screen.getByRole("region", { name: "Todavía no hay cobros" });
    expect(region).toContainElement(
      screen.getByRole("heading", { level: 2, name: "Todavía no hay cobros" }),
    );
    expect(region).toHaveTextContent("Cuando cobres, aparecen acá.");
    // Default icon, hidden from assistive technology.
    expect(region.querySelector('[aria-hidden="true"] svg')).not.toBeNull();
  });

  it("test_AC_PLT_28_empty_state_optional_text_icon_and_action", () => {
    render(
      <EmptyState
        title="Sin integraciones"
        icon={<span data-testid="custom-icon" />}
        action={<Button>Conectá tu primera integración</Button>}
      />,
    );
    expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Conectá tu primera integración" })).toBeEnabled();
    expect(screen.getByRole("region", { name: "Sin integraciones" }).querySelector("p")).toBeNull();
  });
});

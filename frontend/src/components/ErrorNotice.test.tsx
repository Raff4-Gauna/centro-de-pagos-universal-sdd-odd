import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_ERROR_TITLE, ErrorNotice, RETRY_LABEL } from "./ErrorNotice";

describe("ErrorNotice (AC-PLT-28, 07 §2)", () => {
  it("test_AC_PLT_28_error_notice_shows_retry_and_calls_on_retry", async () => {
    const onRetry = vi.fn();
    render(<ErrorNotice message="El servidor no respondió." onRetry={onRetry} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(DEFAULT_ERROR_TITLE);
    expect(alert).toHaveTextContent("El servidor no respondió.");
    expect(RETRY_LABEL).toBe("Reintentar");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("test_AC_PLT_28_error_notice_custom_title_and_retrying_disables_retry", () => {
    render(
      <ErrorNotice title="Error del proveedor" message="Timeout." onRetry={vi.fn()} retrying />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Error del proveedor");
    // While the retry is in flight the button is disabled: no second request on a double click.
    expect(screen.getByRole("button", { name: /Reintentar/ })).toBeDisabled();
  });
});

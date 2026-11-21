import { describe, expect, it } from "vitest";

import {
  BRANCH_FORM_ERRORS,
  branchFieldErrorsFrom,
  changedBranchValues,
  validateBranchValues,
} from "./branch-form";

// The form's check repeats the contract's limits (design.md §5, §6); the backend checks again.
describe("branch-form (RF-TEN-06, design.md §5)", () => {
  it("test_RF_TEN_06_name_required_after_trimming", () => {
    expect(validateBranchValues({ name: "   ", code: "", address: "" })).toEqual({
      name: BRANCH_FORM_ERRORS.nameRequired,
    });
    expect(validateBranchValues({ name: " Centro ", code: "", address: "" })).toEqual({});
  });

  it("test_RF_TEN_06_limits_of_the_contract", () => {
    const errors = validateBranchValues({
      name: "n".repeat(121),
      code: "c".repeat(33),
      address: "a".repeat(256),
    });
    expect(errors).toEqual({
      name: BRANCH_FORM_ERRORS.tooLong(120),
      code: BRANCH_FORM_ERRORS.tooLong(32),
      address: BRANCH_FORM_ERRORS.tooLong(255),
    });
    expect(
      validateBranchValues({
        name: "n".repeat(120),
        code: "c".repeat(32),
        address: "a".repeat(255),
      }),
    ).toEqual({});
  });

  it("test_RF_TEN_06_changes_are_only_the_trimmed_differences", () => {
    const initial = { name: "Centro", code: "C-01", address: "" };
    expect(
      changedBranchValues(initial, { name: " Centro ", code: "", address: "Calle 1 " }),
    ).toEqual({ code: "", address: "Calle 1" });
    expect(changedBranchValues(initial, { ...initial })).toEqual({});
  });

  it("test_RF_TEN_06_server_errors_only_for_form_fields", () => {
    expect(
      branchFieldErrorsFrom([
        { field: "name", code: "taken", message: "Ocupado." },
        { field: "name", code: "other", message: "Segundo." },
        { field: "organization_id", code: "unknown_field", message: "Este campo no se acepta." },
      ]),
    ).toEqual({ name: "Ocupado." });
  });
});

import { describe, expect, it } from "vitest";
import { z } from "zod";

import {
  changedCompanyValues,
  COMPANY_FORM_ERRORS,
  companyFieldErrorsFrom,
  companyResolver,
  type CompanyValues,
  companySchema,
} from "./company-form";

const SAVED: CompanyValues = {
  name: "Acme",
  legal_name: "Acme S.A.",
  tax_id: "30712345671",
  timezone: "America/Argentina/Buenos_Aires",
};

function errorsOf(values: Partial<CompanyValues>) {
  const result = companySchema.safeParse({ ...SAVED, ...values });
  return result.success ? {} : z.flattenError(result.error).fieldErrors;
}

describe("Datos de la empresa: validación (RF-TEN-03, Q-209, design.md §3.9)", () => {
  it("test_RF_TEN_03_schema_trims_and_accepts_the_contract_limits", () => {
    const parsed = companySchema.parse({
      name: `  ${"a".repeat(120)}  `,
      legal_name: "b".repeat(200),
      tax_id: " 30-71234567-1 ",
      timezone: "UTC",
    });
    expect(parsed.name).toBe("a".repeat(120));
    expect(parsed.tax_id).toBe("30-71234567-1");
    expect(errorsOf({ legal_name: "", tax_id: "" })).toEqual({});
  });

  it("test_RF_TEN_03_schema_rejects_what_the_backend_rejects", () => {
    expect(errorsOf({ name: "   " }).name).toEqual([COMPANY_FORM_ERRORS.nameRequired]);
    expect(errorsOf({ name: "a".repeat(121) }).name).toEqual([COMPANY_FORM_ERRORS.tooLong(120)]);
    expect(errorsOf({ legal_name: "b".repeat(201) }).legal_name).toEqual([
      COMPANY_FORM_ERRORS.tooLong(200),
    ]);
    for (const tax_id of [
      "3071234567",
      "307123456712",
      "30-7123456-71",
      "30.71234567.1",
      "٣٠٧١٢٣٤٥٦٧١",
    ]) {
      expect(errorsOf({ tax_id }).tax_id).toEqual([COMPANY_FORM_ERRORS.taxIdInvalid]);
    }
    expect(errorsOf({ timezone: "" }).timezone).toEqual([COMPANY_FORM_ERRORS.timezoneRequired]);
  });

  it("test_RF_TEN_03_resolver_returns_trimmed_values_or_one_message_per_field", async () => {
    const options = { fields: {}, shouldUseNativeValidation: false } as const;
    const ok = await companyResolver({ ...SAVED, name: " Acme 2 " }, undefined, options);
    expect(ok).toEqual({ values: { ...SAVED, name: "Acme 2" }, errors: {} });
    const bad = await companyResolver({ ...SAVED, name: "", tax_id: "x" }, undefined, options);
    expect(bad.values).toEqual({});
    expect(bad.errors.name?.message).toBe(COMPANY_FORM_ERRORS.nameRequired);
    expect(bad.errors.tax_id?.message).toBe(COMPANY_FORM_ERRORS.taxIdInvalid);
    expect(bad.errors.legal_name).toBeUndefined();
  });

  it("test_RF_TEN_03_only_changed_fields_travel", () => {
    expect(changedCompanyValues(SAVED, { ...SAVED, name: " Acme " })).toEqual({});
    // The same CUIT with hyphens is no change: the backend keeps 11 digits.
    expect(changedCompanyValues(SAVED, { ...SAVED, tax_id: "30-71234567-1" })).toEqual({});
    expect(changedCompanyValues(SAVED, { ...SAVED, legal_name: " ", timezone: "UTC" })).toEqual({
      legal_name: "",
      timezone: "UTC",
    });
  });

  it("test_RF_TEN_03_backend_field_errors_map_onto_known_fields_only", () => {
    expect(
      companyFieldErrorsFrom([
        { field: "tax_id", code: "invalid", message: "No es un CUIT válido." },
        { field: "tax_id", code: "other", message: "segundo" },
        { field: "status", code: "unknown_field", message: "Campo desconocido." },
      ]),
    ).toEqual({ tax_id: "No es un CUIT válido." });
  });
});

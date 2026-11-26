import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";
import type { z } from "zod";

// A zod schema as react-hook-form's resolver for a form of flat fields (07 §3.3, Q-239): the
// parsed values when they pass (trimmed, narrowed), the first message of each field when they do
// not. The fields are flat, so the field is the first segment of the issue's path.
export function flatZodResolver<Input extends FieldValues, Output extends FieldValues = Input>(
  schema: z.ZodType<Output, Input>,
): Resolver<Input, unknown, Output> {
  return async (values) => {
    const result = await schema.safeParseAsync(values);
    if (result.success) {
      return { values: result.data, errors: {} };
    }
    const errors: FieldErrors<Input> = {};
    for (const issue of result.error.issues) {
      const field = String(issue.path[0]) as keyof FieldErrors<Input>;
      if (errors[field] === undefined) {
        Object.assign(errors, { [field]: { type: issue.code, message: issue.message } });
      }
    }
    return { values: {}, errors };
  };
}

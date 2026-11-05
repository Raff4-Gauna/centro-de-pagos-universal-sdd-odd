import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

// Place of the company/branch selector (07 §5.1, spec §14): both selects are disabled and empty
// until SPEC-02 brings organizations, memberships and branches. No data is invented here.
export const ORG_BRANCH_PENDING_TEXT = "Disponible con SPEC-02";
const HINT_ID = "org-branch-selector-hint";

const FIELDS = [
  { id: "org-selector", label: "Empresa" },
  { id: "branch-selector", label: "Sucursal" },
] as const;

export function OrgBranchSelectorPlaceholder() {
  return (
    <div
      role="group"
      aria-label="Empresa y sucursal"
      aria-describedby={HINT_ID}
      className="tw-flex tw-items-center tw-gap-2"
    >
      {FIELDS.map((field) => (
        <TextField
          key={field.id}
          id={field.id}
          select
          disabled
          size="small"
          label={field.label}
          value=""
          className="tw-w-32 sm:tw-w-40"
        >
          <MenuItem value="" />
        </TextField>
      ))}
      <Typography
        id={HINT_ID}
        variant="caption"
        color="text.secondary"
        className="tw-hidden lg:tw-block"
      >
        {ORG_BRANCH_PENDING_TEXT}
      </Typography>
    </div>
  );
}

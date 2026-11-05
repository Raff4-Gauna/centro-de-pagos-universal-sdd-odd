import Typography from "@mui/material/Typography";

import { EmptyState } from "@/components/EmptyState";

// Inicio in 00-platform (spec §14, design.md §3.3.2): the collection dashboard of 07 §5.2 needs
// integrations, charges and organizations (SPEC-02/03/04/06), so the page shows an explicit empty
// state with neutral text; never a blank screen nor invented data.
export const HOME_TITLE = "Inicio";
export const HOME_EMPTY_TITLE = "Todavía no hay nada para mostrar";
export const HOME_EMPTY_TEXT =
  "Acá vas a ver el estado de tus integraciones, el resumen del día y la última actividad de cobro.";

export function HomeEmpty() {
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <Typography component="h1" variant="h5">
        {HOME_TITLE}
      </Typography>
      <EmptyState title={HOME_EMPTY_TITLE} description={HOME_EMPTY_TEXT} />
    </div>
  );
}

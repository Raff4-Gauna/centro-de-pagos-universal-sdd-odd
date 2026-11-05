import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";

import { moduleChipLabel, SETTINGS_SECTIONS, type SettingsSection } from "../settings-sections";

// Configuración in 00-platform (spec §14, design.md §3.3.2): the sections of 07 §5.3, all of them
// disabled with a chip of the module that implements them. No links nor actions: nothing works
// before those modules ship, and there is no data to show.
export const SETTINGS_TITLE = "Configuración";
export const SETTINGS_INTRO =
  "Estas secciones se habilitan a medida que se implementa el módulo de cada una.";
export const SETTINGS_LIST_LABEL = "Secciones de configuración";
export const SECTION_UNAVAILABLE_TEXT = "Todavía no disponible.";

function SettingsSectionItem({ section }: Readonly<{ section: SettingsSection }>) {
  const titleId = `settings-section-${section.id}`;
  return (
    <ListItem
      divider
      aria-disabled="true"
      aria-labelledby={titleId}
      data-section={section.id}
      className="tw-flex tw-flex-col tw-items-start tw-gap-2 tw-opacity-60 sm:tw-flex-row sm:tw-items-center"
    >
      <ListItemText
        primary={section.title}
        secondary={`${section.description} ${SECTION_UNAVAILABLE_TEXT}`}
        slotProps={{ primary: { id: titleId } }}
      />
      <Chip size="small" variant="outlined" label={moduleChipLabel(section.modules)} />
    </ListItem>
  );
}

export function SettingsSectionList() {
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <Typography component="h1" variant="h5">
        {SETTINGS_TITLE}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {SETTINGS_INTRO}
      </Typography>
      <List aria-label={SETTINGS_LIST_LABEL} disablePadding>
        {SETTINGS_SECTIONS.map((section) => (
          <SettingsSectionItem key={section.id} section={section} />
        ))}
      </List>
    </div>
  );
}

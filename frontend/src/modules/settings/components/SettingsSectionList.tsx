"use client";

import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import Link from "next/link";

import { moduleChipLabel, SETTINGS_SECTIONS, type SettingsSection } from "../settings-sections";

// Configuración (spec §14, design.md §3.3.2): the sections of 07 §5.3 with a chip of the module
// that implements them. A section whose module shipped links to its page; the rest are disabled,
// with no links nor actions, because nothing works before their module ships. A client component:
// the enabled row is an MUI ListItemButton rendered as a Next Link (a function prop).
export const SETTINGS_TITLE = "Configuración";
export const SETTINGS_INTRO =
  "Estas secciones se habilitan a medida que se implementa el módulo de cada una.";
export const SETTINGS_LIST_LABEL = "Secciones de configuración";
export const SECTION_UNAVAILABLE_TEXT = "Todavía no disponible.";

function EnabledSectionItem({
  section,
  href,
}: Readonly<{ section: SettingsSection; href: string }>) {
  return (
    <ListItem divider disablePadding data-section={section.id}>
      <ListItemButton
        component={Link}
        href={href}
        className="tw-flex tw-flex-col tw-items-start tw-gap-2 sm:tw-flex-row sm:tw-items-center"
      >
        <ListItemText primary={section.title} secondary={section.description} />
        <Chip size="small" variant="outlined" label={moduleChipLabel(section.modules)} />
      </ListItemButton>
    </ListItem>
  );
}

function SettingsSectionItem({ section }: Readonly<{ section: SettingsSection }>) {
  const titleId = `settings-section-${section.id}`;
  if (section.href !== undefined) {
    return <EnabledSectionItem section={section} href={section.href} />;
  }
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

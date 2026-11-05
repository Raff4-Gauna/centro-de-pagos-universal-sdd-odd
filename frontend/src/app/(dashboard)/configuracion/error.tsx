"use client";

import { ErrorNotice } from "@/components/ErrorNotice";

// Error boundary of Configuración (07 §2): an alert with "Reintentar" that re-renders the segment.
// The error's own message is never shown (C-08): it can carry internal details, so the text is fixed.
const SETTINGS_ERROR_MESSAGE =
  "Ocurrió un problema al cargar Configuración. Probá de nuevo en unos segundos.";

export default function SettingsError({
  reset,
}: Readonly<{ error: Error & { digest?: string }; reset: () => void }>) {
  return <ErrorNotice message={SETTINGS_ERROR_MESSAGE} onRetry={reset} />;
}

// Dates of the identity screens (design.md §3.4): `es-AR`, always in Buenos Aires time, whatever
// the zone of the browser, so two people looking at the same session read the same hour.
export const DISPLAY_TIME_ZONE = "America/Argentina/Buenos_Aires";

const FORMAT = new Intl.DateTimeFormat("es-AR", {
  timeZone: DISPLAY_TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

// "19/11/2026, 12:30". An unreadable value shows nothing rather than the raw string.
export function formatDateTime(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? "" : FORMAT.format(date);
}

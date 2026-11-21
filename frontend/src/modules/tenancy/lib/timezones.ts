// The time zones a company can pick in "Datos de la empresa" (Q-240, decided by the owner on
// 2026-11-21): the IANA `America/Argentina/*` zones and `UTC`, with the default first. One list
// for the whole frontend, fixed here rather than taken from the browser (`Intl` gives CLDR aliases
// such as `America/Buenos_Aires` and differs between browsers). The backend still checks every
// value against `zoneinfo`; a zone set another way (by an operator) is kept as the company's
// current value even if it is not here.
export const DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires";

export const COMPANY_TIMEZONES = [
  DEFAULT_TIMEZONE,
  "America/Argentina/Catamarca",
  "America/Argentina/Cordoba",
  "America/Argentina/Jujuy",
  "America/Argentina/La_Rioja",
  "America/Argentina/Mendoza",
  "America/Argentina/Rio_Gallegos",
  "America/Argentina/Salta",
  "America/Argentina/San_Juan",
  "America/Argentina/San_Luis",
  "America/Argentina/Tucuman",
  "America/Argentina/Ushuaia",
  "UTC",
] as const;

export type CompanyTimezone = (typeof COMPANY_TIMEZONES)[number];

export function isCompanyTimezone(value: string): value is CompanyTimezone {
  return (COMPANY_TIMEZONES as readonly string[]).includes(value);
}

// The options of the form: the list, plus the company's current zone at the end when it is not in
// it, so the form shows what is stored without offering it to anyone else.
export function timezoneOptions(current: string): readonly string[] {
  return current === "" || isCompanyTimezone(current)
    ? COMPANY_TIMEZONES
    : [...COMPANY_TIMEZONES, current];
}

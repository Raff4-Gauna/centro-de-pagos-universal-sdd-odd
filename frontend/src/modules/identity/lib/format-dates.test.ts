import { describe, expect, it } from "vitest";

import { DISPLAY_TIME_ZONE, formatDateTime } from "./format-dates";

describe("format-dates (AC-IDA-33, design.md §3.4)", () => {
  it("test_AC_IDA_33_dates_are_shown_in_buenos_aires_time", () => {
    expect(DISPLAY_TIME_ZONE).toBe("America/Argentina/Buenos_Aires");
    // 15:30 UTC is 12:30 in Buenos Aires (UTC-3, no DST).
    expect(formatDateTime("2026-11-19T15:30:00Z")).toBe("19/11/2026, 12:30");
  });

  it("test_AC_IDA_33_dates_change_day_by_buenos_aires_not_utc", () => {
    // 02:00 UTC of the 20th is still the 19th in Buenos Aires.
    expect(formatDateTime("2026-11-20T02:05:00Z")).toBe("19/11/2026, 23:05");
  });

  it("test_AC_IDA_33_an_unreadable_date_is_never_shown_raw", () => {
    expect(formatDateTime("not-a-date")).toBe("");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearStoredToken,
  INVITATION_TOKEN_KEY,
  readStoredToken,
  storeToken,
  takeFragmentToken,
  takeInvitationToken,
} from "./invitation-token";

// RNF-TEN-03, AC-TEN-17, design.md §3.9: the token leaves the URL at once and only waits in the
// tab's storage. Obviously fake tokens.
const FAKE = "fake-invitation-token-for-tests";

function open(url: string) {
  window.history.replaceState(null, "", url);
}

afterEach(() => {
  window.sessionStorage.clear();
  open("/");
});

describe("invitation token (AC-TEN-17, design.md §3.9)", () => {
  it("test_AC_TEN_17_fragment_token_is_read_and_removed_from_the_url", () => {
    open(`/invitacion?x=1#token=${FAKE}`);
    expect(takeFragmentToken()).toBe(FAKE);
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain(FAKE);
    expect(`${window.location.pathname}${window.location.search}`).toBe("/invitacion?x=1");
  });

  it("test_AC_TEN_17_any_fragment_is_removed_even_without_a_token", () => {
    open("/invitacion#otra=cosa");
    expect(takeFragmentToken()).toBeNull();
    expect(window.location.hash).toBe("");
  });

  it.each(["/invitacion", "/invitacion#", "/invitacion#token=", "/invitacion#token=%20"])(
    "test_AC_TEN_17_no_token_in_%s",
    (url) => {
      open(url);
      expect(takeFragmentToken()).toBeNull();
    },
  );

  it("test_AC_TEN_17_url_without_fragment_is_left_alone", () => {
    open("/invitacion");
    const replace = vi.spyOn(window.history, "replaceState");
    takeFragmentToken();
    expect(replace).not.toHaveBeenCalled();
  });

  it("test_AC_TEN_17_token_is_stored_read_and_cleared", () => {
    storeToken(FAKE);
    expect(window.sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBe(FAKE);
    expect(readStoredToken()).toBe(FAKE);
    clearStoredToken();
    expect(window.sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
    expect(readStoredToken()).toBeNull();
  });

  it("test_AC_TEN_17_a_new_link_wins_over_a_stored_token", () => {
    storeToken("fake-older-token");
    open(`/invitacion#token=${FAKE}`);
    expect(takeInvitationToken()).toBe(FAKE);
    open("/invitacion");
    expect(takeInvitationToken()).toBe("fake-older-token");
  });

  it("test_AC_TEN_17_disabled_storage_never_throws", () => {
    const failing = () => {
      throw new Error("storage disabled");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(failing);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(failing);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(failing);
    expect(() => storeToken(FAKE)).not.toThrow();
    expect(readStoredToken()).toBeNull();
    expect(() => clearStoredToken()).not.toThrow();
  });
});

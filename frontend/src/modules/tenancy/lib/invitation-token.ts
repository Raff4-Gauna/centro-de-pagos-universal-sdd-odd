// The token of an invitation link on its way to `POST /api/invitations/accept/` (RNF-TEN-03,
// AC-TEN-17, design.md §3.9, §6). The link is `/invitacion#token=<token>`: in the fragment, which
// the browser never sends to a server, so the token reaches no log, no `Referer` and no
// `return_to`. The page reads it once and takes it out of the address bar right away
// (`history.replaceState`, so "Atrás" and the history never hold it either).
//
// Without a session the person goes through "Ingresar" first, which leaves the site and comes
// back to `/invitacion` (SPEC-01): the token waits in this tab's `sessionStorage` meanwhile, never
// in a cookie nor in the URL. It is kept there while the accept is in flight too (a dead session
// answers `401` and goes to "Ingresar" again) and removed once the backend answered.
export const INVITATION_TOKEN_KEY = "cpu.invitation-token";

const FRAGMENT_PARAMETER = "token";

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    // Storage disabled by the browser: the token only lives in the page's memory.
    return null;
  }
}

function tokenOrNull(value: string | null | undefined): string | null {
  const token = value?.trim();
  return token ? token : null;
}

// The token of the fragment, if any, after taking the whole fragment out of the URL: on this page
// any fragment is the link's, and none is left behind. The path and query stay as they are.
export function takeFragmentToken(): string | null {
  const { hash, pathname, search } = window.location;
  if (hash === "" || hash === "#") {
    return null;
  }
  window.history.replaceState(null, "", `${pathname}${search}`);
  return tokenOrNull(new URLSearchParams(hash.slice(1)).get(FRAGMENT_PARAMETER));
}

export function readStoredToken(): string | null {
  try {
    return tokenOrNull(storage()?.getItem(INVITATION_TOKEN_KEY));
  } catch {
    return null;
  }
}

export function storeToken(token: string): void {
  try {
    storage()?.setItem(INVITATION_TOKEN_KEY, token);
  } catch {
    // Quota or disabled storage: the token is lost if the page has to go through "Ingresar".
  }
}

export function clearStoredToken(): void {
  try {
    storage()?.removeItem(INVITATION_TOKEN_KEY);
  } catch {
    // Disabled storage holds nothing to clear.
  }
}

// The token this visit works with: a link just opened wins over one left by an earlier visit.
export function takeInvitationToken(): string | null {
  return takeFragmentToken() ?? readStoredToken();
}

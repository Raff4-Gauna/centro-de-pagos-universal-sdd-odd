"use client";

import Snackbar from "@mui/material/Snackbar";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import {
  ORG_QUERY_SCOPE,
  setActiveOrganizationId,
  subscribeOrganizationErrors,
  type OrganizationErrorEvent,
} from "@/lib/api-client";

import { organizationsQueryOptions, useOrganizations } from "../hooks/useOrganizations";
import {
  readServerTabOrganization,
  readTabOrganization,
  resolveActiveOrganization,
  saveDefaultOrganization,
  subscribeTabOrganization,
  writeTabOrganization,
} from "../lib/active-organization";

// The company this tab works on (RF-TEN-02, spec §14, Q-119 b, Q-205, design.md §3.9). It resolves
// the tab's value → the BFF's default → the first by name (lib/active-organization.ts), hands it to
// the api-client for `X-Organization-Id`, and keeps the tab's `sessionStorage` in line.
//
// Changing company removes every `['org', …]` query before the first request of the new one, and
// tells the BFF the new default; that default is a preference, so a failed save changes nothing
// for this tab. Global answers about the company (design.md §3.9):
// - `404 organization_not_found` for the company the tab shows: reread the list; if the company
//   is gone, move to the next one and say so, or, with none left, go to "sin organización".
// - `409 organization_suspended`: reread the list, so the status (and SuspendedBanner) is current.
// The UI never decides permissions: this only picks which company the requests name.
export const NO_ORGANIZATION_PATH = "/sin-organizacion";
export const LOST_ACCESS_TEXT = "Ya no tenés acceso a esa empresa";

type ActiveOrgContextValue = Readonly<{
  // null while the list loads, and when the person has no company.
  organizationId: string | null;
  selectOrganization: (organizationId: string) => void;
}>;

const ActiveOrgContext = createContext<ActiveOrgContextValue | null>(null);

export function useActiveOrganization(): ActiveOrgContextValue {
  const value = useContext(ActiveOrgContext);
  if (value === null) {
    throw new Error("useActiveOrganization must be used inside ActiveOrgProvider");
  }
  return value;
}

function sameId(left: string | null, right: string | null): boolean {
  return left !== null && right !== null && left.toLowerCase() === right.toLowerCase();
}

export type ActiveOrgProviderProps = Readonly<{
  // `__Host-cpu_org`, read and checked by the `(dashboard)` layout on the server; null if absent.
  defaultOrganizationId: string | null;
  children: ReactNode;
}>;

export function ActiveOrgProvider({ defaultOrganizationId, children }: ActiveOrgProviderProps) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const organizations = useOrganizations();
  const tabOrganizationId = useSyncExternalStore(
    subscribeTabOrganization,
    readTabOrganization,
    readServerTabOrganization,
  );
  const [lostAccess, setLostAccess] = useState(false);

  const active =
    organizations.data === undefined
      ? null
      : resolveActiveOrganization(organizations.data, tabOrganizationId, defaultOrganizationId);
  const activeId = active?.id ?? null;
  const hasNoOrganization = organizations.data?.length === 0;

  // The company the requests name right now, for the handlers below (they outlive a render).
  const currentRef = useRef<string | null>(null);

  const activate = useCallback(
    (organizationId: string | null) => {
      currentRef.current = organizationId;
      queryClient.removeQueries({ queryKey: [ORG_QUERY_SCOPE] });
      setActiveOrganizationId(organizationId);
      writeTabOrganization(organizationId);
      saveDefaultOrganization(organizationId).catch(() => {
        // Only the default of new tabs is lost; this tab keeps its own value.
      });
    },
    [queryClient],
  );

  const selectOrganization = useCallback(
    (organizationId: string) => {
      if (!sameId(organizationId, currentRef.current)) {
        activate(organizationId);
      }
    },
    [activate],
  );

  useEffect(() => {
    currentRef.current = activeId;
    setActiveOrganizationId(activeId);
    if (activeId !== null && activeId !== tabOrganizationId) {
      writeTabOrganization(activeId);
    }
  }, [activeId, tabOrganizationId]);

  useEffect(() => () => setActiveOrganizationId(null), []);

  useEffect(() => {
    if (hasNoOrganization && pathname !== NO_ORGANIZATION_PATH) {
      router.replace(NO_ORGANIZATION_PATH);
    }
  }, [hasNoOrganization, pathname, router]);

  useEffect(() => {
    async function moveAwayFrom(lostId: string) {
      let list;
      try {
        list = await queryClient.fetchQuery({ ...organizationsQueryOptions(), staleTime: 0 });
      } catch {
        return; // The list itself failed: the selector shows that error with "Reintentar".
      }
      if (!sameId(lostId, currentRef.current) || list.some(({ id }) => sameId(id, lostId))) {
        return; // Already moved by another answer, or the membership is still there.
      }
      const next = resolveActiveOrganization(list, null, defaultOrganizationId);
      activate(next?.id ?? null);
      setLostAccess(next !== null);
    }

    function onOrganizationError({ code, organizationId }: OrganizationErrorEvent) {
      if (!sameId(organizationId, currentRef.current)) {
        return; // About a company the tab already left.
      }
      if (code === "organization_suspended") {
        void queryClient.invalidateQueries({ queryKey: organizationsQueryOptions().queryKey });
      } else if (organizationId !== null) {
        void moveAwayFrom(organizationId);
      }
    }

    return subscribeOrganizationErrors(onOrganizationError);
  }, [activate, defaultOrganizationId, queryClient]);

  const value = useMemo(
    () => ({ organizationId: activeId, selectOrganization }),
    [activeId, selectOrganization],
  );

  return (
    <ActiveOrgContext.Provider value={value}>
      {children}
      <Snackbar
        open={lostAccess}
        autoHideDuration={6000}
        onClose={() => setLostAccess(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        message={LOST_ACCESS_TEXT}
      />
    </ActiveOrgContext.Provider>
  );
}

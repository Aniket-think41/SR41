/**
 * Client-side UI state (frontend spec §6) — server state lives in React Query.
 */

import { create } from "zustand";
import type { Resource, ScopeType } from "./types";

interface DrawerState {
  mode: "detail" | "add" | "edit" | null;
  resource: Resource | null;
  /** default scope for the add form, from the current context */
  scope?: { scope_type: ScopeType; scope_id: string | null };
}

interface UiState {
  orgSlug: string | null;
  setOrgSlug: (slug: string) => void;

  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;

  drawer: DrawerState;
  openDetail: (resource: Resource) => void;
  openAdd: (scope: DrawerState["scope"]) => void;
  openEdit: (resource: Resource) => void;
  closeDrawer: () => void;
}

const ORG_KEY = "skillshare.current_org";

export const useUi = create<UiState>((set) => ({
  orgSlug:
    typeof window !== "undefined" ? window.localStorage.getItem(ORG_KEY) : null,
  setOrgSlug: (slug) => {
    if (typeof window !== "undefined") window.localStorage.setItem(ORG_KEY, slug);
    set({ orgSlug: slug });
  },

  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  paletteOpen: false,
  setPaletteOpen: (open) => set({ paletteOpen: open }),

  drawer: { mode: null, resource: null },
  openDetail: (resource) => set({ drawer: { mode: "detail", resource } }),
  openAdd: (scope) => set({ drawer: { mode: "add", resource: null, scope } }),
  openEdit: (resource) => set({ drawer: { mode: "edit", resource } }),
  closeDrawer: () => set({ drawer: { mode: null, resource: null } }),
}));

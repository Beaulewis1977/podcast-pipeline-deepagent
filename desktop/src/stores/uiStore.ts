/**
 * UI state store for the Podcast Pipeline desktop app.
 *
 * Manages client-side navigation and layout state:
 * - Selected job (the job currently being viewed in detail)
 * - Active view (which of the 4 main views is shown)
 * - Sidebar collapsed/expanded toggle
 */

import { create } from "zustand";

export type ActiveView = "ingestion" | "audio" | "transcript" | "branding";

export interface UIStore {
  selectedJobId: string | null;
  activeView: ActiveView;
  sidebarCollapsed: boolean;
  setSelectedJob: (id: string | null) => void;
  setActiveView: (view: ActiveView) => void;
  toggleSidebar: () => void;
}

export const useUIStore = create<UIStore>((set) => ({
  selectedJobId: null,
  activeView: "ingestion",
  sidebarCollapsed: false,

  setSelectedJob: (id) => set({ selectedJobId: id }),

  setActiveView: (view) => set({ activeView: view }),

  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
}));

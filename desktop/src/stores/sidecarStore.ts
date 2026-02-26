/**
 * Sidecar and backend connection state store.
 *
 * Tracks whether the backend service is reachable, the Tauri sidecar process
 * status, and any connection errors. Components consuming this store can
 * render appropriate loading, connected, or error states without prop drilling.
 */

import { create } from "zustand";
import type { BackendStatus, SidecarStatus } from "../lib/backend";

export interface SidecarStore {
  /** Current backend connectivity status. */
  status: BackendStatus;
  /** Latest sidecar process info from Tauri, or null when unavailable. */
  sidecar: SidecarStatus | null;
  /** Last connection error message, or null when healthy. */
  error: string | null;

  setStatus: (status: BackendStatus) => void;
  setSidecar: (sidecar: SidecarStatus | null) => void;
  setError: (error: string | null) => void;
  /** Mark the backend as connected and clear any prior error. */
  setConnected: () => void;
  /** Mark the backend as disconnected, optionally recording an error. */
  setDisconnected: (error?: string) => void;
}

export const useSidecarStore = create<SidecarStore>((set) => ({
  status: "disconnected",
  sidecar: null,
  error: null,

  setStatus: (status) => set({ status }),

  setSidecar: (sidecar) => set({ sidecar }),

  setError: (error) => set({ error }),

  setConnected: () => set({ status: "connected", error: null }),

  setDisconnected: (error) =>
    set({ status: "disconnected", error: error ?? null }),
}));

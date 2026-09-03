import { create } from "zustand";

/**
 * Reader chrome state that is the same wherever you read and does NOT need to
 * survive a reload.
 *
 * Reading mode, fit and zoom are per-series (`useReaderPreferences`). The
 * page-gap and cinema-mode preferences are per-profile and persisted
 * (`useReaderSettings`). What is left here is the live show/hide of the chrome,
 * which is session-only.
 */
interface ReaderUiState {
  controlsVisible: boolean;
  setControlsVisible: (visible: boolean) => void;
  toggleControls: () => void;
}

export const useReaderStore = create<ReaderUiState>((set) => ({
  controlsVisible: true,
  setControlsVisible: (visible) => set({ controlsVisible: visible }),
  toggleControls: () => set((state) => ({ controlsVisible: !state.controlsVisible })),
}));

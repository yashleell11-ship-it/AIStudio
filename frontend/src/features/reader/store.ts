import { create } from "zustand";

const PAGE_GAP_STORAGE_KEY = "manhwamaniacs-reader-page-gap";

/**
 * Reader chrome state that is the same wherever you read.
 *
 * Reading mode, fit and zoom deliberately do NOT live here — those are chosen
 * per series and are owned by `useReaderPreferences`.
 */
interface ReaderUiState {
  controlsVisible: boolean;
  pageGap: boolean;
  setControlsVisible: (visible: boolean) => void;
  toggleControls: () => void;
  setPageGap: (enabled: boolean) => void;
  togglePageGap: () => void;
}

function readInitialPageGap(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(PAGE_GAP_STORAGE_KEY) === "1";
}

function persistPageGap(enabled: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PAGE_GAP_STORAGE_KEY, enabled ? "1" : "0");
}

export const useReaderStore = create<ReaderUiState>((set) => ({
  controlsVisible: true,
  pageGap: readInitialPageGap(),
  setControlsVisible: (visible) => set({ controlsVisible: visible }),
  toggleControls: () => set((state) => ({ controlsVisible: !state.controlsVisible })),
  setPageGap: (enabled) => {
    persistPageGap(enabled);
    set({ pageGap: enabled });
  },
  togglePageGap: () =>
    set((state) => {
      const next = !state.pageGap;
      persistPageGap(next);
      return { pageGap: next };
    }),
}));

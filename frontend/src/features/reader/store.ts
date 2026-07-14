import { create } from "zustand";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.1;

const PAGE_GAP_STORAGE_KEY = "manhwamaniacs-reader-page-gap";

interface ReaderUiState {
  controlsVisible: boolean;
  zoomLevel: number;
  pageGap: boolean;
  setControlsVisible: (visible: boolean) => void;
  toggleControls: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  setZoomLevel: (zoom: number) => void;
  setPageGap: (enabled: boolean) => void;
  togglePageGap: () => void;
}

function clampZoom(zoom: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(zoom.toFixed(2))));
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
  zoomLevel: 1,
  pageGap: readInitialPageGap(),
  setControlsVisible: (visible) => set({ controlsVisible: visible }),
  toggleControls: () => set((state) => ({ controlsVisible: !state.controlsVisible })),
  zoomIn: () => set((state) => ({ zoomLevel: clampZoom(state.zoomLevel + ZOOM_STEP) })),
  zoomOut: () => set((state) => ({ zoomLevel: clampZoom(state.zoomLevel - ZOOM_STEP) })),
  resetZoom: () => set({ zoomLevel: 1 }),
  setZoomLevel: (zoom) => set({ zoomLevel: clampZoom(zoom) }),
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

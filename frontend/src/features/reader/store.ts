import { create } from "zustand";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.1;

interface ReaderUiState {
  controlsVisible: boolean;
  zoomLevel: number;
  setControlsVisible: (visible: boolean) => void;
  toggleControls: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  setZoomLevel: (zoom: number) => void;
}

function clampZoom(zoom: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(zoom.toFixed(2))));
}

export const useReaderStore = create<ReaderUiState>((set) => ({
  controlsVisible: true,
  zoomLevel: 1,
  setControlsVisible: (visible) => set({ controlsVisible: visible }),
  toggleControls: () => set((state) => ({ controlsVisible: !state.controlsVisible })),
  zoomIn: () => set((state) => ({ zoomLevel: clampZoom(state.zoomLevel + ZOOM_STEP) })),
  zoomOut: () => set((state) => ({ zoomLevel: clampZoom(state.zoomLevel - ZOOM_STEP) })),
  resetZoom: () => set({ zoomLevel: 1 }),
  setZoomLevel: (zoom) => set({ zoomLevel: clampZoom(zoom) }),
}));

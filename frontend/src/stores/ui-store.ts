import { create } from "zustand";

/**
 * Global UI/client state (not server data — that lives in TanStack Query).
 * Keep this lean: only cross-cutting interface state belongs here.
 */
interface UiState {
  sidebarCollapsed: boolean;
  mobileSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  closeMobileSidebar: () => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  sidebarCollapsed: false,
  mobileSidebarOpen: false,
  toggleSidebar: () => {
    if (typeof window !== "undefined" && window.matchMedia("(max-width: 1023px)").matches) {
      set({ mobileSidebarOpen: !get().mobileSidebarOpen });
      return;
    }
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
  },
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),
  closeMobileSidebar: () => set({ mobileSidebarOpen: false }),
}));

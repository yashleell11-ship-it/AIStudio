import { create } from "zustand";

/**
 * Global UI/client state (not server data — that lives in TanStack Query).
 * Keep this lean: only cross-cutting interface state belongs here.
 */
interface UiState {
  sidebarCollapsed: boolean;
  mobileSidebarOpen: boolean;
  /**
   * The `?` keyboard cheat-sheet. Shared state rather than a local flag because
   * three unrelated places open the same sheet: the shell's `?` binding, the
   * topbar button, and the reader (whose Escape handling also has to know the
   * sheet is up so Esc closes it before leaving the chapter).
   */
  shortcutsOpen: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  closeMobileSidebar: () => void;
  toggleShortcuts: () => void;
  closeShortcuts: () => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  sidebarCollapsed: false,
  mobileSidebarOpen: false,
  shortcutsOpen: false,
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
  toggleShortcuts: () => set((state) => ({ shortcutsOpen: !state.shortcutsOpen })),
  closeShortcuts: () => set({ shortcutsOpen: false }),
}));

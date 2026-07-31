import { LibraryShelfView } from "@/features/library";

/**
 * The Library tab: followed series only. The full, filterable catalogue lives
 * one level down at /library/browse — the same split the mobile client makes
 * between `DashboardScreen` and `LibraryScreen`.
 */
export default function LibraryPage() {
  return <LibraryShelfView />;
}

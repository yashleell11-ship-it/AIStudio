import { ProfilesSettingsPanel } from "@/features/profiles";

export default function ManageProfilesPage() {
  return (
    <div className="page-shell">
      <div className="page-container mx-auto max-w-3xl">
        <div className="mb-8">
          <h1 className="font-display text-4xl tracking-wide text-fg">Profiles</h1>
          <p className="mt-1 text-sm text-muted">
            Create, edit, and switch the reading profiles for your account.
          </p>
        </div>
        <ProfilesSettingsPanel />
      </div>
    </div>
  );
}

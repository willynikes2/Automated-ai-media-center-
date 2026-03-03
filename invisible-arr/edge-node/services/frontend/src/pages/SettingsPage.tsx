import { QualityPrefs } from '@/components/settings/QualityPrefs';
import { StoragePrefs } from '@/components/settings/StoragePrefs';
import { AccountSettings } from '@/components/settings/AccountSettings';

export function SettingsPage() {
  return (
    <div className="px-4 md:px-8 py-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-sm text-text-secondary">Configure your media preferences and account.</p>
      </div>

      <QualityPrefs />
      <StoragePrefs />
      <AccountSettings />
    </div>
  );
}

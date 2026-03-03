import { QualityPrefs } from '@/components/settings/QualityPrefs';
import { StoragePrefs } from '@/components/settings/StoragePrefs';
import { AccountSettings } from '@/components/settings/AccountSettings';
import { QuickConnect } from '@/components/jellyfin/QuickConnect';
import { Card } from '@/components/ui/Card';
import { useStorageInfo } from '@/hooks/useMedia';
import { HardDrive } from 'lucide-react';

function StorageDisplay() {
  const { data, isLoading } = useStorageInfo();

  if (isLoading || !data) return null;

  const pct = data.total_gb > 0 ? (data.used_gb / data.total_gb) * 100 : 0;
  const color = pct > 90 ? 'bg-status-failed' : pct > 70 ? 'bg-yellow-500' : 'bg-status-available';

  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <HardDrive className="h-5 w-5" /> Storage
      </h2>

      <div className="space-y-3">
        <div className="h-3 bg-bg-tertiary rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(100, pct)}%` }} />
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-text-tertiary text-xs">Used</p>
            <p className="font-medium">{data.used_gb.toFixed(1)} GB</p>
          </div>
          <div>
            <p className="text-text-tertiary text-xs">Free</p>
            <p className="font-medium">{data.free_gb.toFixed(1)} GB</p>
          </div>
          <div>
            <p className="text-text-tertiary text-xs">Media</p>
            <p className="font-medium">{data.media_gb.toFixed(1)} GB</p>
          </div>
          <div>
            <p className="text-text-tertiary text-xs">Total</p>
            <p className="font-medium">{data.total_gb.toFixed(1)} GB</p>
          </div>
        </div>

        <p className="text-xs text-text-tertiary">{data.prune_policy}</p>
      </div>
    </Card>
  );
}

export function SettingsPage() {
  return (
    <div className="px-4 md:px-8 py-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-sm text-text-secondary">Configure your media preferences and account.</p>
      </div>

      <StorageDisplay />
      <QualityPrefs />
      <StoragePrefs />
      <AccountSettings />

      <Card className="p-5">
        <h2 className="text-lg font-semibold mb-1">Device Pairing</h2>
        <p className="text-xs text-text-secondary mb-4">
          Use Quick Connect to link external devices like TVs and streaming boxes to your Jellyfin account.
        </p>
        <QuickConnect />
      </Card>
    </div>
  );
}

import { useState } from 'react';
import { SourceManager } from '@/components/iptv/SourceManager';
import { ChannelGrid } from '@/components/iptv/ChannelGrid';
import { EPGPreview } from '@/components/iptv/EPGPreview';
import { EPGGuide } from '@/components/iptv/EPGGuide';
import { useAuthStore } from '@/stores/authStore';

interface TabDef {
  key: string;
  label: string;
  adminOnly?: boolean;
}

const tabs: TabDef[] = [
  { key: 'channels', label: 'Channels' },
  { key: 'guide', label: 'Guide' },
  { key: 'sources', label: 'Sources', adminOnly: true },
  { key: 'setup', label: 'Setup', adminOnly: true },
];

export function IPTVPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const visibleTabs = tabs.filter((t) => !t.adminOnly || isAdmin);

  const [tab, setTab] = useState<string>('channels');

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">Live TV</h1>
      <p className="text-sm text-text-secondary mb-6">Manage your IPTV sources, channels, and Live TV integration.</p>

      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit mb-6">
        {visibleTabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-accent text-white' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'channels' && <ChannelGrid />}
      {tab === 'guide' && <EPGGuide />}
      {isAdmin && tab === 'sources' && <SourceManager />}
      {isAdmin && tab === 'setup' && <EPGPreview />}
    </div>
  );
}

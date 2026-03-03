import { useState } from 'react';
import { SourceManager } from '@/components/iptv/SourceManager';
import { ChannelGrid } from '@/components/iptv/ChannelGrid';
import { EPGPreview } from '@/components/iptv/EPGPreview';
import { EPGGuide } from '@/components/iptv/EPGGuide';

const tabs = [
  { key: 'channels', label: 'Channels' },
  { key: 'guide', label: 'Guide' },
  { key: 'sources', label: 'Sources' },
  { key: 'setup', label: 'Setup' },
] as const;

export function IPTVPage() {
  const [tab, setTab] = useState<string>('channels');

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">Live TV</h1>
      <p className="text-sm text-text-secondary mb-6">Manage your IPTV sources, channels, and Jellyfin integration.</p>

      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit mb-6">
        {tabs.map((t) => (
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
      {tab === 'sources' && <SourceManager />}
      {tab === 'setup' && <EPGPreview />}
    </div>
  );
}

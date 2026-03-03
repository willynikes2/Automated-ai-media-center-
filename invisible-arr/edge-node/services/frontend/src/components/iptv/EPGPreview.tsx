import { Card } from '@/components/ui/Card';
import { useAuthStore } from '@/stores/authStore';
import { Copy, Check } from 'lucide-react';
import { useState } from 'react';

export function EPGPreview() {
  const apiKey = useAuthStore((s) => s.apiKey);
  const [copied, setCopied] = useState<string | null>(null);

  const baseUrl = window.location.origin;
  const m3uUrl = `${baseUrl}/iptv/playlist.m3u?user_token=${apiKey}`;
  const epgUrl = `${baseUrl}/iptv/epg.xml?user_token=${apiKey}&tz=America/New_York`;

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="space-y-4">
      <h3 className="font-semibold">Jellyfin Live TV Setup</h3>
      <p className="text-sm text-text-secondary">
        Add these URLs to Jellyfin under Dashboard → Live TV to enable IPTV channels.
      </p>

      <Card className="p-4 space-y-3">
        <div>
          <label className="text-xs text-text-tertiary uppercase tracking-wider">M3U Tuner URL</label>
          <div className="flex items-center gap-2 mt-1">
            <code className="text-xs bg-bg-tertiary rounded px-2 py-1.5 flex-1 truncate">{m3uUrl}</code>
            <button onClick={() => copy(m3uUrl, 'm3u')} className="p-2 rounded-lg hover:bg-bg-tertiary text-text-secondary">
              {copied === 'm3u' ? <Check className="h-4 w-4 text-status-available" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div>
          <label className="text-xs text-text-tertiary uppercase tracking-wider">EPG / XMLTV URL</label>
          <div className="flex items-center gap-2 mt-1">
            <code className="text-xs bg-bg-tertiary rounded px-2 py-1.5 flex-1 truncate">{epgUrl}</code>
            <button onClick={() => copy(epgUrl, 'epg')} className="p-2 rounded-lg hover:bg-bg-tertiary text-text-secondary">
              {copied === 'epg' ? <Check className="h-4 w-4 text-status-available" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </Card>

      <Card className="p-4">
        <h4 className="text-sm font-medium mb-2">Setup Steps</h4>
        <ol className="text-sm text-text-secondary space-y-1.5 list-decimal list-inside">
          <li>Open Jellyfin Dashboard → Live TV</li>
          <li>Click "Add" under Tuner Devices → select "M3U Tuner" → paste the M3U URL above</li>
          <li>Click "Add" under TV Guide Data Providers → select "XMLTV" → paste the EPG URL above</li>
          <li>Click "Refresh Guide Data" to load channels and EPG</li>
        </ol>
      </Card>
    </div>
  );
}

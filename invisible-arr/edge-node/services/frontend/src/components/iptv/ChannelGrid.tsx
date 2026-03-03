import { useState } from 'react';
import { Toggle } from '@/components/ui/Toggle';
import { Card } from '@/components/ui/Card';
import { useChannels, useBulkUpdateChannels } from '@/hooks/useIPTV';
import { toast } from '@/components/ui/Toast';
import { Tv } from 'lucide-react';

export function ChannelGrid({ sourceId }: { sourceId?: string }) {
  const { data: channels, isLoading } = useChannels({ source_id: sourceId });
  const bulkUpdate = useBulkUpdateChannels();
  const [filter, setFilter] = useState('');

  const filtered = channels?.filter((ch) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return ch.name.toLowerCase().includes(q) || ch.group_title?.toLowerCase().includes(q);
  }) ?? [];

  const groups = [...new Set(filtered.map((ch) => ch.group_title ?? 'Ungrouped'))].sort();

  const toggleChannel = (id: string, enabled: boolean) => {
    bulkUpdate.mutate([{ id, enabled }], {
      onError: () => toast('Failed to update channel', 'error'),
    });
  };

  if (isLoading) return <p className="text-sm text-text-secondary">Loading channels...</p>;
  if (!channels?.length) return <p className="text-sm text-text-secondary">No channels found.</p>;

  return (
    <div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter channels..."
        className="w-full bg-bg-tertiary border border-white/10 rounded-lg px-3 py-2 text-sm text-text-primary mb-4"
      />

      <p className="text-xs text-text-tertiary mb-4">{filtered.length} of {channels.length} channels</p>

      {groups.map((group) => {
        const groupChannels = filtered.filter((ch) => (ch.group_title ?? 'Ungrouped') === group);
        if (!groupChannels.length) return null;

        return (
          <div key={group} className="mb-6">
            <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">{group} ({groupChannels.length})</h4>
            <div className="space-y-1">
              {groupChannels.slice(0, 50).map((ch) => (
                <div key={ch.id} className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-bg-tertiary/50">
                  {ch.logo ? (
                    <img src={ch.logo} alt="" className="h-6 w-6 rounded object-contain bg-bg-tertiary" />
                  ) : (
                    <Tv className="h-5 w-5 text-text-tertiary" />
                  )}
                  <span className="text-sm flex-1 truncate">{ch.preferred_name ?? ch.name}</span>
                  {ch.channel_number && <span className="text-xs text-text-tertiary">#{ch.channel_number}</span>}
                  <Toggle checked={ch.enabled} onChange={(v) => toggleChannel(ch.id, v)} />
                </div>
              ))}
              {groupChannels.length > 50 && (
                <p className="text-xs text-text-tertiary px-2">...and {groupChannels.length - 50} more</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

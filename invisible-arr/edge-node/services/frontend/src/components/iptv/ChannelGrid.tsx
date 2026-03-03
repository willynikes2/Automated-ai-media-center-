import { useState } from 'react';
import { Toggle } from '@/components/ui/Toggle';
import { Card } from '@/components/ui/Card';
import { useChannels, useBulkUpdateChannels } from '@/hooks/useIPTV';
import { toast } from '@/components/ui/Toast';
import { Tv, Play, Search } from 'lucide-react';

export function ChannelGrid({ sourceId }: { sourceId?: string }) {
  const { data: channels, isLoading } = useChannels({ source_id: sourceId });
  const bulkUpdate = useBulkUpdateChannels();
  const [filter, setFilter] = useState('');
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  const filtered = channels?.filter((ch) => {
    if (!filter && !selectedGroup) return true;
    const q = filter.toLowerCase();
    const matchesFilter = !filter || ch.name.toLowerCase().includes(q) || ch.group_title?.toLowerCase().includes(q);
    const matchesGroup = !selectedGroup || (ch.group_title ?? 'Ungrouped') === selectedGroup;
    return matchesFilter && matchesGroup;
  }) ?? [];

  const allGroups = [...new Set(channels?.map((ch) => ch.group_title ?? 'Ungrouped') ?? [])].sort();

  const toggleChannel = (id: string, enabled: boolean) => {
    bulkUpdate.mutate([{ id, enabled }], {
      onError: () => toast('Failed to update channel', 'error'),
    });
  };

  const handleWatch = (streamUrl: string) => {
    window.open(streamUrl, '_blank');
  };

  if (isLoading) return <p className="text-sm text-text-secondary">Loading channels...</p>;
  if (!channels?.length) return <p className="text-sm text-text-secondary">No channels found. Add a source first.</p>;

  return (
    <div>
      {/* Search + Group filter */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-tertiary" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search channels..."
            className="w-full bg-bg-tertiary border border-white/10 rounded-lg pl-10 pr-3 py-2 text-sm text-text-primary"
          />
        </div>
        <select
          value={selectedGroup ?? ''}
          onChange={(e) => setSelectedGroup(e.target.value || null)}
          className="bg-bg-tertiary border border-white/10 rounded-lg px-3 py-2 text-sm text-text-primary"
        >
          <option value="">All Groups ({channels.length})</option>
          {allGroups.map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
      </div>

      <p className="text-xs text-text-tertiary mb-4">{filtered.length} channels</p>

      {/* Channel cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {filtered.slice(0, 100).map((ch) => (
          <Card key={ch.id} className="p-3 flex items-center gap-3">
            {/* Logo */}
            <div className="shrink-0 h-12 w-12 rounded-lg bg-bg-tertiary flex items-center justify-center overflow-hidden">
              {ch.logo ? (
                <img src={ch.logo} alt="" className="h-full w-full object-contain" />
              ) : (
                <Tv className="h-6 w-6 text-text-tertiary" />
              )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{ch.preferred_name ?? ch.name}</p>
              <p className="text-[10px] text-text-tertiary truncate">
                {ch.group_title ?? 'Ungrouped'}
                {ch.channel_number && ` · #${ch.channel_number}`}
              </p>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => handleWatch(ch.stream_url)}
                className="p-2 rounded-lg bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
                title="Watch"
              >
                <Play className="h-4 w-4" />
              </button>
              <Toggle checked={ch.enabled} onChange={(v) => toggleChannel(ch.id, v)} />
            </div>
          </Card>
        ))}
      </div>

      {filtered.length > 100 && (
        <p className="text-xs text-text-tertiary mt-4 text-center">
          Showing 100 of {filtered.length} channels. Use search to narrow results.
        </p>
      )}
    </div>
  );
}

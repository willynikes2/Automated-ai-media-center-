import { useState, useMemo } from 'react';
import { useLibrary, useStorageInfo } from '@/hooks/useMedia';
import { FullSpinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Library, HardDrive } from 'lucide-react';
import { Link } from 'react-router-dom';

const tabs = [
  { key: 'Movie', label: 'Movies' },
  { key: 'Series', label: 'TV Shows' },
] as const;

type SortKey = 'DateCreated' | 'SortName' | 'ProductionYear';

function StorageBar({ usedGb, totalGb }: { usedGb: number; totalGb: number }) {
  if (totalGb <= 0) return null;
  const pct = Math.min(100, (usedGb / totalGb) * 100);
  const color = pct > 90 ? 'bg-status-failed' : pct > 70 ? 'bg-yellow-500' : 'bg-status-available';

  return (
    <div className="flex items-center gap-3">
      <HardDrive className="h-4 w-4 text-text-tertiary shrink-0" />
      <div className="flex-1 h-2 bg-bg-tertiary rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-text-secondary whitespace-nowrap">
        {usedGb.toFixed(0)} / {totalGb.toFixed(0)} GB ({pct.toFixed(0)}%)
      </span>
    </div>
  );
}

function ResolutionOverlay({ item }: { item: any }) {
  const stream = item.MediaSources?.[0]?.MediaStreams?.find((s: any) => s.Type === 'Video');
  const width = stream?.Width ?? 0;
  let label = '';
  let cls = '';
  if (width >= 3800) { label = '4K'; cls = 'bg-yellow-500/90'; }
  else if (width >= 1900) { label = '1080p'; cls = 'bg-blue-500/90'; }
  else if (width >= 1200) { label = '720p'; cls = 'bg-green-500/90'; }
  if (!label) return null;
  return (
    <span className={`absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold text-white ${cls}`}>
      {label}
    </span>
  );
}

export function LibraryPage() {
  const [tab, setTab] = useState<'Movie' | 'Series'>('Movie');
  const [sortBy, setSortBy] = useState<SortKey>('DateCreated');
  const [resFilter, setResFilter] = useState<string>('any');
  const { data: storageData } = useStorageInfo();

  const { data, isLoading } = useLibrary(tab, {
    SortBy: `${sortBy},SortName`,
    SortOrder: sortBy === 'SortName' ? 'Ascending' : 'Descending',
    Limit: 100,
  });

  const items = data?.Items ?? [];

  const filteredItems = useMemo(() => {
    if (resFilter === 'any') return items;
    return items.filter((item: any) => {
      const width = item.MediaSources?.[0]?.MediaStreams?.find((s: any) => s.Type === 'Video')?.Width ?? 0;
      if (resFilter === '4k') return width >= 3800;
      if (resFilter === '1080p') return width >= 1900 && width < 3800;
      if (resFilter === '720p') return width >= 1200 && width < 1900;
      return true;
    });
  }, [items, resFilter]);

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">Library</h1>
      <p className="text-sm text-text-secondary mb-4">Browse your Jellyfin media library.</p>

      {/* Storage bar */}
      {storageData && (
        <div className="mb-4">
          <StorageBar usedGb={storageData.used_gb} totalGb={storageData.total_gb} />
        </div>
      )}

      {/* Tabs + filters */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-6">
        <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
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

        <div className="flex gap-2 ml-auto">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="bg-bg-tertiary border border-white/10 rounded-lg px-3 py-1.5 text-xs text-text-primary"
          >
            <option value="DateCreated">Date Added</option>
            <option value="SortName">Name</option>
            <option value="ProductionYear">Year</option>
          </select>
          <select
            value={resFilter}
            onChange={(e) => setResFilter(e.target.value)}
            className="bg-bg-tertiary border border-white/10 rounded-lg px-3 py-1.5 text-xs text-text-primary"
          >
            <option value="any">All Quality</option>
            <option value="4k">4K</option>
            <option value="1080p">1080p</option>
            <option value="720p">720p</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <FullSpinner />
      ) : !filteredItems.length ? (
        <EmptyState icon={Library} title="Nothing here yet" description={resFilter !== 'any' ? 'No items match your filter.' : 'Your Jellyfin library is empty.'} />
      ) : (
        <>
          <p className="text-xs text-text-tertiary mb-3">{filteredItems.length} items</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {filteredItems.map((item: any) => {
              const imgTag = item.ImageTags?.Primary;
              const poster = imgTag
                ? `/jellyfin/Items/${item.Id}/Images/Primary?maxHeight=400&tag=${imgTag}`
                : null;
              const sizeBytes = item.MediaSources?.[0]?.Size ?? 0;
              const sizeGb = sizeBytes > 0 ? (sizeBytes / (1024 ** 3)).toFixed(1) : null;

              return (
                <Link key={item.Id} to={`/library/${item.Id}`} className="group block rounded-xl overflow-hidden hover:ring-1 hover:ring-accent/30 transition-all">
                  <div className="relative aspect-[2/3] bg-bg-tertiary">
                    {poster ? (
                      <img src={poster} alt={item.Name} loading="lazy" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-text-tertiary text-sm">No Poster</div>
                    )}
                    <ResolutionOverlay item={item} />
                  </div>
                  <div className="p-2">
                    <h3 className="text-sm font-medium truncate">{item.Name}</h3>
                    <div className="flex items-center gap-2">
                      <p className="text-xs text-text-tertiary">{item.ProductionYear ?? ''}</p>
                      {sizeGb && <p className="text-[10px] text-text-tertiary">{sizeGb} GB</p>}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

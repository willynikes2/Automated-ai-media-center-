import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useLibrary, useStorageInfo } from '@/hooks/useMedia';
import { FullSpinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Library, HardDrive, Film, Tv } from 'lucide-react';
import type { LibraryItem } from '@/api/media';

const tabs = [
  { key: 'all', label: 'All' },
  { key: 'movie', label: 'Movies' },
  { key: 'tv', label: 'TV Shows' },
] as const;

type Tab = (typeof tabs)[number]['key'];

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

function formatSize(bytes: number): string {
  if (bytes <= 0) return '';
  const gb = bytes / (1024 ** 3);
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / (1024 ** 2)).toFixed(0)} MB`;
}

function MediaCard({ item }: { item: LibraryItem }) {
  const isMovie = item.media_type === 'movie';
  const Icon = isMovie ? Film : Tv;

  return (
    <Link
      to={`/search?q=${encodeURIComponent(item.title)}`}
      className="group block rounded-xl overflow-hidden ring-1 ring-white/5 hover:ring-accent/30 transition-all"
    >
      <div className="relative aspect-[2/3] bg-bg-tertiary flex items-center justify-center">
        <Icon className="h-12 w-12 text-text-tertiary/30" />
        {item.year && (
          <span className="absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold text-white bg-accent/80">
            {item.year}
          </span>
        )}
      </div>
      <div className="p-2">
        <h3 className="text-sm font-medium truncate">{item.title}</h3>
        <div className="flex items-center gap-2">
          <p className="text-xs text-text-tertiary capitalize">{item.media_type}</p>
          {item.size_bytes > 0 && <p className="text-[10px] text-text-tertiary">{formatSize(item.size_bytes)}</p>}
        </div>
        <p className="text-[10px] text-text-tertiary/60 truncate mt-0.5">{item.file_name}</p>
      </div>
    </Link>
  );
}

export function LibraryPage() {
  const [tab, setTab] = useState<Tab>('all');
  const { data: storageData } = useStorageInfo();
  const mediaType = tab === 'all' ? undefined : (tab as 'movie' | 'tv');
  const { data, isLoading } = useLibrary(mediaType);

  const items = data?.items ?? [];
  const moviesCount = data?.movies_count ?? 0;
  const tvCount = data?.tv_count ?? 0;

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">My Library</h1>
      <p className="text-sm text-text-secondary mb-4">Your personal media collection.</p>

      {/* Storage bar */}
      {storageData && (
        <div className="mb-4">
          <StorageBar usedGb={storageData.used_gb} totalGb={storageData.total_gb} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-6">
        <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
          {tabs.map((t) => {
            const count = t.key === 'all' ? moviesCount + tvCount : t.key === 'movie' ? moviesCount : tvCount;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  tab === t.key ? 'bg-accent text-white' : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {t.label}
                {count > 0 && <span className="ml-1 text-xs opacity-70">({count})</span>}
              </button>
            );
          })}
        </div>
      </div>

      {isLoading ? (
        <FullSpinner />
      ) : !items.length ? (
        <EmptyState
          icon={Library}
          title="Nothing here yet"
          description="Request something from Discover to build your library."
        />
      ) : (
        <>
          <p className="text-xs text-text-tertiary mb-3">{items.length} items</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {items.map((item) => (
              <MediaCard key={item.file_path} item={item} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

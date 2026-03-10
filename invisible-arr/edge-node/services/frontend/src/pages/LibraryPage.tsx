import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useJellyfinLibrary, useQuotaInfo } from '@/hooks/useMedia';
import { FullSpinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Library, Film, Tv, Star } from 'lucide-react';
import type { JellyfinLibraryItem } from '@/api/media';

const tabs = [
  { key: 'all', label: 'All' },
  { key: 'movie', label: 'Movies' },
  { key: 'tv', label: 'TV Shows' },
] as const;

type Tab = (typeof tabs)[number]['key'];

function QuotaBar({ label, count, quota }: { label: string; count: number; quota: number }) {
  if (quota === 0) return null;
  const isUnlimited = quota === -1;
  const pct = isUnlimited ? 0 : Math.min(100, (count / quota) * 100);
  const color = pct > 90 ? 'bg-status-failed' : pct > 70 ? 'bg-yellow-500' : 'bg-accent';

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-text-tertiary w-16 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        {!isUnlimited && (
          <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
        )}
      </div>
      <span className="text-text-secondary whitespace-nowrap">
        {count}{isUnlimited ? '' : ` / ${quota}`}
      </span>
    </div>
  );
}

function PosterCard({ item }: { item: JellyfinLibraryItem }) {
  const imgTag = item.ImageTags?.Primary;
  const poster = imgTag ? `/jellyfin/Items/${item.Id}/Images/Primary?maxHeight=450&tag=${imgTag}` : null;
  const isMovie = item.Type === 'Movie';

  return (
    <Link
      to={`/library/${item.Id}`}
      className="group relative rounded-xl overflow-hidden ring-1 ring-white/5 hover:ring-accent/40 hover:scale-[1.02] transition-all duration-200"
    >
      <div className="relative aspect-[2/3] bg-bg-tertiary">
        {poster ? (
          <img
            src={poster}
            alt={item.Name}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            {isMovie ? <Film className="h-12 w-12 text-text-tertiary/30" /> : <Tv className="h-12 w-12 text-text-tertiary/30" />}
          </div>
        )}

        {/* Hover overlay with info */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

        {/* Bottom info on hover */}
        <div className="absolute bottom-0 left-0 right-0 p-2.5 translate-y-2 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all duration-200">
          {item.CommunityRating != null && (
            <div className="flex items-center gap-1 mb-1">
              <Star className="h-3 w-3 text-yellow-400 fill-yellow-400" />
              <span className="text-xs text-white/90 font-medium">{item.CommunityRating.toFixed(1)}</span>
            </div>
          )}
          {item.ProductionYear && (
            <span className="text-xs text-white/70">{item.ProductionYear}</span>
          )}
        </div>

        {/* Type badge */}
        <div className="absolute top-1.5 right-1.5">
          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold text-white/90 bg-black/50 backdrop-blur-sm">
            {isMovie ? 'MOVIE' : 'TV'}
          </span>
        </div>
      </div>

      {/* Title below poster */}
      <div className="p-2 bg-bg-secondary">
        <h3 className="text-sm font-medium truncate">{item.Name}</h3>
      </div>
    </Link>
  );
}

export function LibraryPage() {
  const [tab, setTab] = useState<Tab>('all');
  const mediaType = tab === 'all' ? undefined : (tab as 'movie' | 'tv');
  const { data, isLoading } = useJellyfinLibrary(mediaType);
  const { data: quota } = useQuotaInfo();

  const items = data?.Items ?? [];
  const movieCount = tab === 'all' && data
    ? items.filter((i) => i.Type === 'Movie').length
    : undefined;
  const tvCount = tab === 'all' && data
    ? items.filter((i) => i.Type === 'Series').length
    : undefined;

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">My Library</h1>
      <p className="text-sm text-text-secondary mb-4">Your personal media collection.</p>

      {/* Quota bars */}
      {quota && (
        <div className="mb-5 space-y-1.5 max-w-sm">
          <QuotaBar label="Movies" count={quota.movie_count} quota={quota.movie_quota} />
          <QuotaBar label="TV Shows" count={quota.tv_count} quota={quota.tv_quota} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit mb-6">
        {tabs.map((t) => {
          const count = t.key === 'all'
            ? items.length
            : t.key === 'movie'
            ? (movieCount ?? 0)
            : (tvCount ?? 0);
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

      {isLoading ? (
        <FullSpinner />
      ) : !items.length ? (
        <EmptyState
          icon={Library}
          title="Nothing here yet"
          description="Request something from Discover to build your library."
        />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7 gap-4">
          {items.map((item) => (
            <PosterCard key={item.Id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

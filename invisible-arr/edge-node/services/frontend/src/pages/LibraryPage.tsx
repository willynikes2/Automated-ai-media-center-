import { useState } from 'react';
import { useLibrary } from '@/hooks/useMedia';
import { FullSpinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Library } from 'lucide-react';
import { posterUrl } from '@/api/client';
import { Link } from 'react-router-dom';

const tabs = [
  { key: 'Movie', label: 'Movies' },
  { key: 'Series', label: 'TV Shows' },
] as const;

export function LibraryPage() {
  const [tab, setTab] = useState<'Movie' | 'Series'>('Movie');
  const { data, isLoading } = useLibrary(tab);

  const items = data?.Items ?? [];

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">Library</h1>
      <p className="text-sm text-text-secondary mb-6">Browse your Jellyfin media library.</p>

      {/* Tabs */}
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

      {isLoading ? (
        <FullSpinner />
      ) : !items.length ? (
        <EmptyState icon={Library} title="Nothing here yet" description="Your Jellyfin library is empty." />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {items.map((item: any) => {
            const imgTag = item.ImageTags?.Primary;
            const poster = imgTag
              ? `/jellyfin/Items/${item.Id}/Images/Primary?maxHeight=400&tag=${imgTag}`
              : null;

            return (
              <div key={item.Id} className="group block rounded-xl overflow-hidden">
                <div className="relative aspect-[2/3] bg-bg-tertiary">
                  {poster ? (
                    <img src={poster} alt={item.Name} loading="lazy" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-text-tertiary text-sm">No Poster</div>
                  )}
                </div>
                <div className="p-2">
                  <h3 className="text-sm font-medium truncate">{item.Name}</h3>
                  <p className="text-xs text-text-tertiary">{item.ProductionYear ?? ''}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

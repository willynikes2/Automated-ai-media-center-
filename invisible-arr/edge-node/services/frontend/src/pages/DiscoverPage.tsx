import { useState } from 'react';
import { useTrending, usePopular } from '@/hooks/useMedia';
import { useProviders, useCatalogRows } from '@/hooks/useCatalog';
import { MediaRow } from '@/components/media/MediaGrid';
import { ProviderChips } from '@/components/catalog/ProviderChips';
import { CatalogRow } from '@/components/catalog/CatalogRow';
import { Button } from '@/components/ui/Button';
import { FullSpinner } from '@/components/ui/Spinner';
import { backdropUrl } from '@/api/client';
import { Star, Download } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { TMDBResult } from '@/api/media';

function HeroSection({ item }: { item: TMDBResult }) {
  const title = item.title ?? item.name ?? '';
  const type = item.media_type ?? (item.title ? 'movie' : 'tv');
  const backdrop = backdropUrl(item.backdrop_path, 'w1280');
  const navigate = useNavigate();

  return (
    <div className="relative h-[400px] md:h-[500px] -mt-px mb-8">
      {backdrop ? (
        <img src={backdrop} alt="" className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full bg-bg-tertiary" />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-bg-primary via-bg-primary/50 to-transparent" />
      <div className="absolute inset-0 bg-gradient-to-r from-bg-primary/80 to-transparent" />

      <div className="absolute bottom-8 left-4 md:left-8 right-4 max-w-xl">
        <h2 className="text-3xl md:text-4xl font-bold mb-2">{title}</h2>
        <div className="flex items-center gap-3 mb-3 text-sm text-text-secondary">
          {item.vote_average > 0 && (
            <span className="flex items-center gap-1">
              <Star className="h-4 w-4 text-yellow-400 fill-yellow-400" />
              {item.vote_average.toFixed(1)}
            </span>
          )}
          <span>{(item.release_date ?? item.first_air_date ?? '').slice(0, 4)}</span>
          <span>{type === 'movie' ? 'Movie' : 'TV Show'}</span>
        </div>
        <p className="text-sm text-text-secondary line-clamp-2 mb-4">{item.overview}</p>
        <div className="flex gap-3">
          <Button onClick={() => navigate(`/media/${type}/${item.id}`)} size="lg">
            <Download className="h-4 w-4" /> Request
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/media/${type}/${item.id}`)} size="lg">
            More Info
          </Button>
        </div>
      </div>
    </div>
  );
}

function AllContent() {
  const { data: trendingMovies, isLoading } = useTrending('movie');
  const { data: trendingTV } = useTrending('tv');
  const { data: popularMovies } = usePopular('movie');
  const { data: popularTV } = usePopular('tv');

  if (isLoading) return <FullSpinner />;

  return (
    <>
      {trendingMovies?.[0] && <HeroSection item={trendingMovies[0]} />}
      <div className="px-4 md:px-8 space-y-2">
        <MediaRow title="Trending Movies" items={trendingMovies?.slice(1) ?? []} />
        <MediaRow title="Trending TV Shows" items={trendingTV ?? []} />
        <MediaRow title="Popular Movies" items={popularMovies ?? []} />
        <MediaRow title="Popular TV Shows" items={popularTV ?? []} />
      </div>
    </>
  );
}

function ProviderContent({ providerId }: { providerId: number }) {
  const { data: rows, isLoading } = useCatalogRows(providerId);

  if (isLoading) return <FullSpinner />;
  if (!rows?.length) return <p className="px-8 text-text-secondary">No content found.</p>;

  return (
    <div className="px-4 md:px-8 space-y-2 mt-4">
      {rows.map((row, i) => (
        <CatalogRow key={row.slug} row={row} providerId={providerId} eager={i < 3} />
      ))}
      <p className="text-center text-xs text-text-tertiary py-4">
        Data provided by TMDB
      </p>
    </div>
  );
}

export function DiscoverPage() {
  const [selectedProvider, setSelectedProvider] = useState<number | null>(null);
  const { data: providers } = useProviders();

  return (
    <div>
      <div className="pt-4 mb-4">
        <ProviderChips
          providers={providers ?? []}
          selected={selectedProvider}
          onSelect={setSelectedProvider}
        />
      </div>

      {selectedProvider === null ? <AllContent /> : <ProviderContent providerId={selectedProvider} />}
    </div>
  );
}

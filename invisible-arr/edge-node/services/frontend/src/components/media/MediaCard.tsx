import { Link } from 'react-router-dom';
import { Star } from 'lucide-react';
import { posterUrl } from '@/api/client';
import type { TMDBResult } from '@/api/media';

interface Props {
  item: TMDBResult;
  className?: string;
}

export function MediaCard({ item, className = '' }: Props) {
  const type = item.media_type ?? (item.title ? 'movie' : 'tv');
  const title = item.title ?? item.name ?? 'Unknown';
  const year = (item.release_date ?? item.first_air_date ?? '').slice(0, 4);
  const poster = posterUrl(item.poster_path);

  return (
    <Link
      to={`/media/${type}/${item.id}`}
      className={`group block rounded-xl overflow-hidden transition-transform hover:scale-[1.03] ${className}`}
    >
      <div className="relative aspect-[2/3] bg-bg-tertiary">
        {poster ? (
          <img src={poster} alt={title} loading="lazy" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-text-tertiary text-sm">
            No Poster
          </div>
        )}

        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

        {/* Rating badge */}
        {item.vote_average > 0 && (
          <div className="absolute top-2 right-2 flex items-center gap-1 bg-black/70 backdrop-blur-sm rounded-md px-1.5 py-0.5">
            <Star className="h-3 w-3 text-yellow-400 fill-yellow-400" />
            <span className="text-xs font-medium">{item.vote_average.toFixed(1)}</span>
          </div>
        )}
      </div>

      <div className="p-2">
        <h3 className="text-sm font-medium truncate group-hover:text-accent transition-colors">{title}</h3>
        <p className="text-xs text-text-tertiary">{year || 'Unknown year'}</p>
      </div>
    </Link>
  );
}

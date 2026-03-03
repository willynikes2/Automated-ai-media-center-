import { Star, Clock, Calendar } from 'lucide-react';
import { backdropUrl, posterUrl } from '@/api/client';
import { RequestButton } from './RequestButton';

interface Props {
  detail: {
    id: number;
    title?: string;
    name?: string;
    overview: string;
    poster_path: string | null;
    backdrop_path: string | null;
    vote_average: number;
    release_date?: string;
    first_air_date?: string;
    runtime?: number;
    number_of_seasons?: number;
    genres?: { id: number; name: string }[];
    credits?: { cast?: { id: number; name: string; character: string; profile_path: string | null }[] };
  };
  type: 'movie' | 'tv';
}

export function MediaDetail({ detail, type }: Props) {
  const title = detail.title ?? detail.name ?? 'Unknown';
  const year = (detail.release_date ?? detail.first_air_date ?? '').slice(0, 4);
  const backdrop = backdropUrl(detail.backdrop_path);
  const poster = posterUrl(detail.poster_path, 'w500');
  const cast = detail.credits?.cast?.slice(0, 8) ?? [];

  return (
    <div>
      {/* Backdrop */}
      <div className="relative h-[300px] md:h-[400px] -mt-px">
        {backdrop ? (
          <img src={backdrop} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full bg-bg-tertiary" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-bg-primary via-bg-primary/60 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-bg-primary/80 to-transparent" />
      </div>

      {/* Content */}
      <div className="relative -mt-40 px-4 md:px-8 max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row gap-6 md:gap-8">
          {/* Poster */}
          <div className="w-48 md:w-56 shrink-0 mx-auto md:mx-0">
            <div className="aspect-[2/3] rounded-xl overflow-hidden shadow-2xl border border-white/10">
              {poster ? (
                <img src={poster} alt={title} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full bg-bg-tertiary flex items-center justify-center text-text-tertiary">
                  No Poster
                </div>
              )}
            </div>
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl md:text-4xl font-bold mb-2">{title}</h1>

            <div className="flex flex-wrap items-center gap-3 mb-4 text-sm text-text-secondary">
              {year && (
                <span className="flex items-center gap-1">
                  <Calendar className="h-4 w-4" /> {year}
                </span>
              )}
              {detail.runtime && (
                <span className="flex items-center gap-1">
                  <Clock className="h-4 w-4" /> {detail.runtime} min
                </span>
              )}
              {detail.number_of_seasons && (
                <span>{detail.number_of_seasons} Season{detail.number_of_seasons > 1 ? 's' : ''}</span>
              )}
              {detail.vote_average > 0 && (
                <span className="flex items-center gap-1">
                  <Star className="h-4 w-4 text-yellow-400 fill-yellow-400" />
                  {detail.vote_average.toFixed(1)}
                </span>
              )}
            </div>

            {/* Genres */}
            {detail.genres && detail.genres.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-4">
                {detail.genres.map((g) => (
                  <span key={g.id} className="px-2.5 py-1 rounded-full bg-bg-tertiary text-xs text-text-secondary border border-white/5">
                    {g.name}
                  </span>
                ))}
              </div>
            )}

            {/* Overview */}
            <p className="text-text-secondary text-sm leading-relaxed mb-6 max-w-2xl">{detail.overview}</p>

            {/* Request button */}
            <RequestButton tmdbId={detail.id} title={title} mediaType={type} />
          </div>
        </div>

        {/* Cast */}
        {cast.length > 0 && (
          <div className="mt-10">
            <h3 className="text-lg font-semibold mb-3">Cast</h3>
            <div className="scroll-row">
              {cast.map((c) => (
                <div key={c.id} className="w-[100px] shrink-0 text-center">
                  <div className="w-20 h-20 mx-auto rounded-full overflow-hidden bg-bg-tertiary mb-2">
                    {c.profile_path ? (
                      <img src={`https://image.tmdb.org/t/p/w185${c.profile_path}`} alt={c.name} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-text-tertiary text-xs">?</div>
                    )}
                  </div>
                  <p className="text-xs font-medium truncate">{c.name}</p>
                  <p className="text-[10px] text-text-tertiary truncate">{c.character}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

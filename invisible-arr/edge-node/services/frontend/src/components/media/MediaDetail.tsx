import { useState } from 'react';
import { Star, Clock, Calendar, Play, ChevronDown, ChevronUp, Download, Tv } from 'lucide-react';
import { backdropUrl, posterUrl } from '@/api/client';
import { RequestButton } from './RequestButton';
import { TrailerPlayer } from './TrailerPlayer';
import { SeasonPicker } from './SeasonPicker';
import { Button } from '@/components/ui/Button';

interface Props {
  detail: {
    id: number;
    title?: string;
    name?: string;
    overview: string;
    poster_path: string | null;
    backdrop_path: string | null;
    vote_average: number;
    vote_count?: number;
    release_date?: string;
    first_air_date?: string;
    runtime?: number;
    number_of_seasons?: number;
    tagline?: string;
    status?: string;
    genres?: { id: number; name: string }[];
    created_by?: { name: string }[];
    credits?: {
      cast?: { id: number; name: string; character: string; profile_path: string | null }[];
      crew?: { id: number; name: string; job: string; profile_path: string | null }[];
    };
    videos?: {
      results?: { key: string; site: string; type: string; name: string; official: boolean }[];
    };
  };
  type: 'movie' | 'tv';
}

export function MediaDetail({ detail, type }: Props) {
  const [showTrailer, setShowTrailer] = useState(false);
  const [overviewExpanded, setOverviewExpanded] = useState(false);

  const title = detail.title ?? detail.name ?? 'Unknown';
  const year = (detail.release_date ?? detail.first_air_date ?? '').slice(0, 4);
  const backdrop = backdropUrl(detail.backdrop_path);
  const poster = posterUrl(detail.poster_path, 'w500');
  const cast = detail.credits?.cast?.slice(0, 10) ?? [];

  // Director for movies, creator for TV
  const director = type === 'movie'
    ? detail.credits?.crew?.find((c) => c.job === 'Director')?.name
    : detail.created_by?.map((c) => c.name).join(', ');
  const directorLabel = type === 'movie' ? 'Director' : 'Creator';

  const hasTrailerVideos = detail.videos?.results?.some(
    (v) => v.site === 'YouTube' && v.type === 'Trailer',
  );

  const overviewTruncated = detail.overview.length > 300 && !overviewExpanded;
  const displayOverview = overviewTruncated
    ? detail.overview.slice(0, 300) + '...'
    : detail.overview;

  return (
    <div className="pb-8">
      {/* Backdrop */}
      <div className="relative h-[350px] md:h-[500px] -mt-px">
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
            <h1 className="text-2xl md:text-4xl font-bold mb-1">{title}</h1>

            {/* Tagline */}
            {detail.tagline && (
              <p className="text-sm italic text-text-secondary mb-3">{detail.tagline}</p>
            )}

            {/* Meta row */}
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
                  {detail.vote_count != null && (
                    <span className="text-text-tertiary">({detail.vote_count.toLocaleString()} votes)</span>
                  )}
                </span>
              )}
            </div>

            {/* Director / Creator */}
            {director && (
              <p className="text-sm text-text-secondary mb-3">
                <span className="text-text-tertiary">{directorLabel}:</span> {director}
              </p>
            )}

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

            {/* Trailer player (inline, above overview) */}
            {showTrailer && (
              <TrailerPlayer videos={detail.videos} onClose={() => setShowTrailer(false)} />
            )}

            {/* Overview */}
            {detail.overview && (
              <div className="mb-6 max-w-2xl">
                <p className="text-text-secondary text-sm leading-relaxed">
                  {displayOverview}
                </p>
                {detail.overview.length > 300 && (
                  <button
                    onClick={() => setOverviewExpanded(!overviewExpanded)}
                    className="text-accent text-xs mt-1 hover:underline"
                  >
                    {overviewExpanded ? 'Show Less' : 'Read More'}
                  </button>
                )}
              </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-3 flex-wrap">
              <RequestButton tmdbId={detail.id} title={title} mediaType={type} />
              {hasTrailerVideos && (
                <Button
                  variant="secondary"
                  size="lg"
                  onClick={() => setShowTrailer(!showTrailer)}
                >
                  <Play className="h-4 w-4" />
                  {showTrailer ? 'Hide Trailer' : 'Play Trailer'}
                </Button>
              )}
            </div>

            {/* Season/Episode picker for TV shows */}
            {type === 'tv' && (
              <div className="mt-6">
                <SeasonPicker tmdbId={detail.id} title={title} />
              </div>
            )}
          </div>
        </div>

        {/* Cast */}
        {cast.length > 0 && (
          <div className="mt-10">
            <h3 className="text-lg font-semibold mb-3">Cast</h3>
            <div className="scroll-row">
              {cast.map((c) => (
                <div key={c.id} className="w-[120px] shrink-0 text-center">
                  <div className="aspect-[2/3] rounded-lg overflow-hidden bg-bg-tertiary mb-2">
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

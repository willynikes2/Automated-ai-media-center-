import { useState } from 'react';
import { ChevronDown, ChevronUp, Download, Tv, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useTVSeasons, useTVSeasonDetail } from '@/hooks/useMedia';
import { useCreateRequest, useBatchRequest } from '@/hooks/useJobs';
import { toast } from '@/components/ui/Toast';
import type { TVSeason } from '@/api/media';

interface Props {
  tmdbId: number;
  title: string;
}

function EpisodeList({ tmdbId, season, title }: { tmdbId: number; season: number; title: string }) {
  const { data, isLoading } = useTVSeasonDetail(tmdbId, season);
  const mutation = useCreateRequest();
  const [requested, setRequested] = useState<Set<number>>(new Set());

  const handleEpisodeRequest = (episodeNum: number) => {
    mutation.mutate(
      {
        tmdb_id: tmdbId,
        media_type: 'tv',
        query: title,
        season,
        episode: episodeNum,
      },
      {
        onSuccess: () => {
          setRequested((prev) => new Set(prev).add(episodeNum));
          toast(`Requested ${title} S${String(season).padStart(2, '0')}E${String(episodeNum).padStart(2, '0')}`, 'success');
        },
        onError: (err: any) => {
          toast(err?.response?.data?.detail ?? 'Request failed', 'error');
        },
      },
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 px-4 text-sm text-text-secondary">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading episodes...
      </div>
    );
  }

  const episodes = data?.episodes ?? [];

  return (
    <div className="divide-y divide-white/5">
      {episodes.map((ep) => (
        <div key={ep.episode_number} className="flex items-center gap-3 py-2.5 px-4 hover:bg-white/[0.02]">
          <span className="text-xs text-text-tertiary font-mono w-8 shrink-0">
            E{String(ep.episode_number).padStart(2, '0')}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-sm truncate">{ep.name || `Episode ${ep.episode_number}`}</p>
            {ep.runtime && (
              <span className="text-[10px] text-text-tertiary">{ep.runtime} min</span>
            )}
          </div>
          <button
            onClick={() => handleEpisodeRequest(ep.episode_number)}
            disabled={requested.has(ep.episode_number) || mutation.isPending}
            className={`shrink-0 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
              requested.has(ep.episode_number)
                ? 'bg-status-available/20 text-status-available cursor-default'
                : 'bg-accent/10 text-accent hover:bg-accent/20'
            }`}
          >
            {requested.has(ep.episode_number) ? 'Requested' : 'Request'}
          </button>
        </div>
      ))}
    </div>
  );
}

function SeasonRow({ tmdbId, season, title, onSeasonRequest, seasonRequested }: {
  tmdbId: number;
  season: TVSeason;
  title: string;
  onSeasonRequest: (seasonNum: number) => void;
  seasonRequested: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-white/5 overflow-hidden">
      <div className="flex items-center gap-3 p-3 bg-bg-secondary">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 flex-1 min-w-0 text-left"
        >
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-text-tertiary shrink-0" />
          ) : (
            <ChevronDown className="h-4 w-4 text-text-tertiary shrink-0" />
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium">{season.name}</p>
            <p className="text-[10px] text-text-tertiary">
              {season.episode_count} episode{season.episode_count !== 1 ? 's' : ''}
              {season.air_date && ` · ${season.air_date.slice(0, 4)}`}
            </p>
          </div>
        </button>
        <button
          onClick={() => onSeasonRequest(season.season_number)}
          disabled={seasonRequested}
          className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            seasonRequested
              ? 'bg-status-available/20 text-status-available cursor-default'
              : 'bg-accent/10 text-accent hover:bg-accent/20'
          }`}
        >
          <Download className="h-3 w-3" />
          {seasonRequested ? 'Requested' : 'Request Season'}
        </button>
      </div>
      {expanded && (
        <EpisodeList tmdbId={tmdbId} season={season.season_number} title={title} />
      )}
    </div>
  );
}

export function SeasonPicker({ tmdbId, title }: Props) {
  const { data, isLoading } = useTVSeasons(tmdbId);
  const batchMutation = useBatchRequest();
  const [requestedSeasons, setRequestedSeasons] = useState<Set<number>>(new Set());
  const [allRequested, setAllRequested] = useState(false);

  const seasons = data?.seasons ?? [];

  const handleSeasonRequest = (seasonNum: number) => {
    batchMutation.mutate(
      { tmdb_id: tmdbId, query: title, seasons: [seasonNum] },
      {
        onSuccess: () => {
          setRequestedSeasons((prev) => new Set(prev).add(seasonNum));
          toast(`Requested ${title} Season ${seasonNum}`, 'success');
        },
        onError: (err: any) => {
          toast(err?.response?.data?.detail ?? 'Request failed', 'error');
        },
      },
    );
  };

  const handleAllSeasons = () => {
    batchMutation.mutate(
      { tmdb_id: tmdbId, query: title },
      {
        onSuccess: (jobs) => {
          setAllRequested(true);
          toast(`Requested ${title} — ${jobs.length} seasons queued`, 'success');
        },
        onError: (err: any) => {
          toast(err?.response?.data?.detail ?? 'Request failed', 'error');
        },
      },
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-text-secondary py-4">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading seasons...
      </div>
    );
  }

  if (!seasons.length) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-1.5">
          <Tv className="h-4 w-4 text-text-tertiary" />
          Seasons & Episodes
        </h3>
        <Button
          size="sm"
          onClick={handleAllSeasons}
          disabled={allRequested || batchMutation.isPending}
          loading={batchMutation.isPending}
        >
          <Download className="h-3.5 w-3.5" />
          {allRequested ? 'All Requested' : `Request All ${seasons.length} Seasons`}
        </Button>
      </div>
      <div className="space-y-2">
        {seasons.map((s) => (
          <SeasonRow
            key={s.season_number}
            tmdbId={tmdbId}
            season={s}
            title={title}
            onSeasonRequest={handleSeasonRequest}
            seasonRequested={allRequested || requestedSeasons.has(s.season_number)}
          />
        ))}
      </div>
    </div>
  );
}

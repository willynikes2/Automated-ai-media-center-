import { Download, Check, Search, HardDrive, Zap, Server, Star, Play } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { useCreateRequest } from '@/hooks/useJobs';
import { toast } from '@/components/ui/Toast';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { searchReleases, type ReleaseResult } from '@/api/search';

interface Props {
  tmdbId: number;
  title: string;
  mediaType: 'movie' | 'tv';
}

const DOWNLOADER_LABELS: Record<string, { label: string; icon: typeof Zap }> = {
  rd: { label: 'Real-Debrid', icon: Zap },
  torrent: { label: 'Torrent (VPN)', icon: Server },
};

function ResolutionBadge({ resolution }: { resolution: number }) {
  const colors: Record<number, string> = {
    2160: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    1080: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    720: 'bg-green-500/20 text-green-400 border-green-500/30',
    480: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };
  const cls = colors[resolution] || colors[480];
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${cls}`}>
      {resolution}p
    </span>
  );
}

function StorageHint({ sizeGb, freeGb }: { sizeGb: number; freeGb: number }) {
  if (freeGb <= 0 || sizeGb <= 0) return null;
  const pct = (sizeGb / freeGb) * 100;
  const color = pct > 10 ? 'text-yellow-400' : 'text-text-tertiary';
  return (
    <span className={`text-[10px] ${color}`}>
      <HardDrive className="h-3 w-3 inline mr-0.5" />
      {sizeGb.toFixed(1)} GB ({pct.toFixed(1)}% of free)
    </span>
  );
}

function ReleaseRow({
  release,
  isRecommended,
  selected,
  onClick,
  storageFreeGb,
}: {
  release: ReleaseResult;
  isRecommended: boolean;
  selected: boolean;
  onClick: () => void;
  storageFreeGb: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg border transition-all ${
        selected
          ? 'border-accent bg-accent/10'
          : 'border-white/5 bg-bg-secondary hover:border-white/10'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium truncate">{release.title}</p>
          <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
            <ResolutionBadge resolution={release.resolution} />
            <span className="text-[10px] text-text-tertiary">{release.source}</span>
            <span className="text-[10px] text-text-tertiary">{release.codec}</span>
            {release.audio !== 'unknown' && (
              <span className="text-[10px] text-text-tertiary">{release.audio}</span>
            )}
            <span className="text-[10px] text-text-tertiary">{release.seeders} seeds</span>
          </div>
          <div className="flex items-center gap-3 mt-1">
            <StorageHint sizeGb={release.size_gb} freeGb={storageFreeGb} />
            <div className="flex gap-1">
              {release.downloaders.map((d) => (
                <span key={d} className="text-[9px] px-1 py-0.5 rounded bg-bg-tertiary text-text-tertiary">
                  {DOWNLOADER_LABELS[d]?.label ?? d}
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {isRecommended && (
            <span className="flex items-center gap-0.5 text-[9px] font-semibold text-accent">
              <Star className="h-3 w-3 fill-accent" /> Best
            </span>
          )}
          <span className="text-xs font-mono text-text-secondary">{release.score}</span>
        </div>
      </div>
    </button>
  );
}

export function RequestButton({ tmdbId, title, mediaType }: Props) {
  const mutation = useCreateRequest();
  const [requested, setRequested] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [selectedDownloader, setSelectedDownloader] = useState<string | null>(null);
  const [acquisitionMode, setAcquisitionMode] = useState<'download' | 'stream'>('download');

  const searchQuery = useQuery({
    queryKey: ['search-releases', title, mediaType],
    queryFn: () => searchReleases(title, mediaType),
    enabled: showModal,
    staleTime: 60_000,
  });

  const data = searchQuery.data;
  const results = data?.results ?? [];
  const recommended = data?.recommended_index ?? null;
  const rdAvailable = data?.downloaders_available?.includes('rd') ?? false;

  const handleOpen = () => {
    setShowModal(true);
    setSelectedIdx(null);
    setSelectedDownloader(null);
    setAcquisitionMode('download');
  };

  const handleRequest = () => {
    const release = selectedIdx != null ? results[selectedIdx] : null;
    mutation.mutate(
      {
        tmdb_id: tmdbId,
        media_type: mediaType,
        query: title,
        preferred_resolution: release?.resolution,
        preferred_downloader: selectedDownloader as 'rd' | 'torrent' | undefined,
        acquisition_mode: acquisitionMode,
      },
      {
        onSuccess: () => {
          setRequested(true);
          setShowModal(false);
          toast(`${acquisitionMode === 'stream' ? 'Stream' : 'Download'} requested for "${title}"`, 'success');
        },
        onError: (err: any) => {
          toast(err?.response?.data?.detail ?? 'Request failed', 'error');
        },
      },
    );
  };

  // Quick request (skip modal)
  const handleQuickRequest = () => {
    mutation.mutate(
      { tmdb_id: tmdbId, media_type: mediaType, query: title },
      {
        onSuccess: () => {
          setRequested(true);
          toast(`Requested "${title}"`, 'success');
        },
        onError: (err: any) => {
          toast(err?.response?.data?.detail ?? 'Request failed', 'error');
        },
      },
    );
  };

  if (requested) {
    return (
      <Button variant="secondary" disabled>
        <Check className="h-4 w-4" /> Requested
      </Button>
    );
  }

  return (
    <>
      <div className="flex items-center gap-2">
        <Button onClick={handleOpen} size="lg">
          <Download className="h-4 w-4" />
          Request {mediaType === 'movie' ? 'Movie' : 'Series'}
        </Button>
        <Button variant="secondary" size="lg" onClick={handleQuickRequest} loading={mutation.isPending && !showModal}>
          <Zap className="h-4 w-4" /> Quick
        </Button>
      </div>

      <Modal open={showModal} onClose={() => setShowModal(false)} title={`Request: ${title}`}>
        <div className="space-y-4 max-h-[70vh] overflow-y-auto">
          {/* Download / Stream toggle */}
          <div className="flex gap-1 bg-bg-tertiary rounded-lg p-1">
            <button
              onClick={() => {
                setAcquisitionMode('download');
              }}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                acquisitionMode === 'download'
                  ? 'bg-accent text-white'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <HardDrive className="h-4 w-4" /> Download
            </button>
            <button
              onClick={() => {
                setAcquisitionMode('stream');
                if (rdAvailable) setSelectedDownloader('rd');
              }}
              disabled={!rdAvailable}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                acquisitionMode === 'stream'
                  ? 'bg-accent text-white'
                  : rdAvailable
                  ? 'text-text-secondary hover:text-text-primary'
                  : 'text-text-tertiary/50 cursor-not-allowed'
              }`}
            >
              <Play className="h-4 w-4" /> Stream
            </button>
          </div>
          {acquisitionMode === 'stream' && (
            <p className="text-[10px] text-text-tertiary">
              Stream uses Real-Debrid for instant playback without saving to disk.
            </p>
          )}
          {!rdAvailable && (
            <p className="text-[10px] text-text-tertiary">
              Streaming requires Real-Debrid to be enabled.
            </p>
          )}

          {/* Search status */}
          {searchQuery.isLoading && (
            <div className="flex items-center gap-2 text-sm text-text-secondary py-8 justify-center">
              <Search className="h-4 w-4 animate-spin" />
              Searching for available releases...
            </div>
          )}

          {searchQuery.isError && (
            <div className="text-sm text-status-failed py-4 text-center">
              Search failed. You can still request — the system will find the best release automatically.
            </div>
          )}

          {/* Results */}
          {results.length > 0 && (
            <>
              <div className="flex items-center justify-between">
                <p className="text-xs text-text-secondary">
                  {results.length} releases found
                  {data && ` (${data.storage_free_gb} GB free)`}
                </p>
              </div>

              <div className="space-y-2">
                {results.slice(0, 15).map((r, i) => (
                  <ReleaseRow
                    key={r.info_hash || i}
                    release={r}
                    isRecommended={i === recommended}
                    selected={selectedIdx === i}
                    onClick={() => {
                      setSelectedIdx(i);
                      if (acquisitionMode === 'stream') {
                        setSelectedDownloader('rd');
                      } else if (!selectedDownloader && r.downloaders.length > 0) {
                        setSelectedDownloader(r.downloaders[0]);
                      }
                    }}
                    storageFreeGb={data?.storage_free_gb ?? 0}
                  />
                ))}
              </div>
            </>
          )}

          {!searchQuery.isLoading && results.length === 0 && !searchQuery.isError && (
            <div className="text-sm text-text-secondary py-4 text-center">
              No releases found yet. The system will keep searching after you request.
            </div>
          )}

          {/* Downloader selection (only for download mode) */}
          {acquisitionMode === 'download' && selectedIdx != null && results[selectedIdx]?.downloaders.length > 1 && (
            <div>
              <p className="text-xs font-medium text-text-secondary mb-2">Download with</p>
              <div className="flex gap-2">
                {results[selectedIdx].downloaders.map((d) => {
                  const info = DOWNLOADER_LABELS[d];
                  return (
                    <button
                      key={d}
                      onClick={() => setSelectedDownloader(d)}
                      className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm transition-all ${
                        selectedDownloader === d
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-white/5 bg-bg-secondary text-text-secondary hover:border-white/10'
                      }`}
                    >
                      {info && <info.icon className="h-4 w-4" />}
                      {info?.label ?? d}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action */}
          <div className="flex justify-end gap-2 pt-2 border-t border-white/5">
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleRequest} loading={mutation.isPending}>
              {acquisitionMode === 'stream' ? <Play className="h-4 w-4" /> : <Download className="h-4 w-4" />}
              {selectedIdx != null
                ? `${acquisitionMode === 'stream' ? 'Stream' : 'Request'} ${results[selectedIdx].resolution}p · ${results[selectedIdx].size_gb.toFixed(1)} GB`
                : `${acquisitionMode === 'stream' ? 'Stream' : 'Request'} (Auto Select)`}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

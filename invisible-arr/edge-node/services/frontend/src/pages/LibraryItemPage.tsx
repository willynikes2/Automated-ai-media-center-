import { useParams, useNavigate } from 'react-router-dom';
import { useJellyfinItem, useDeleteJellyfinItem } from '@/hooks/useMedia';
import { FullSpinner } from '@/components/ui/Spinner';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { toast } from '@/components/ui/Toast';
import { ArrowLeft, Play, Trash2, RefreshCw, HardDrive, Star, Clock } from 'lucide-react';
import { useState } from 'react';

function ResolutionBadge({ width }: { width: number }) {
  let label = 'SD';
  let cls = 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  if (width >= 3800) {
    label = '4K';
    cls = 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
  } else if (width >= 1900) {
    label = '1080p';
    cls = 'bg-blue-500/20 text-blue-400 border-blue-500/30';
  } else if (width >= 1200) {
    label = '720p';
    cls = 'bg-green-500/20 text-green-400 border-green-500/30';
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold border ${cls}`}>{label}</span>
  );
}

function GenrePill({ genre }: { genre: string }) {
  return (
    <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-white/5 text-text-secondary border border-white/10">
      {genre}
    </span>
  );
}

function FileDetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-2 border-b border-white/5 last:border-b-0">
      <span className="text-xs text-text-tertiary">{label}</span>
      <span className="text-xs text-text-secondary font-medium">{value}</span>
    </div>
  );
}

export function LibraryItemPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: item, isLoading } = useJellyfinItem(id!);
  const deleteMutation = useDeleteJellyfinItem();
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [overviewExpanded, setOverviewExpanded] = useState(false);

  if (isLoading) return <FullSpinner />;
  if (!item) {
    return (
      <div className="px-4 md:px-8 py-6 text-center">
        <p className="text-text-secondary">Item not found.</p>
        <Button variant="secondary" className="mt-4" onClick={() => navigate('/library')}>
          <ArrowLeft className="h-4 w-4" /> Back to Library
        </Button>
      </div>
    );
  }

  const mediaSource = item.MediaSources?.[0];
  const videoStream = mediaSource?.MediaStreams?.find((s: any) => s.Type === 'Video');
  const audioStream = mediaSource?.MediaStreams?.find((s: any) => s.Type === 'Audio');
  const subtitleStream = mediaSource?.MediaStreams?.find((s: any) => s.Type === 'Subtitle');
  const sizeBytes = mediaSource?.Size ?? 0;
  const sizeGb = sizeBytes > 0 ? (sizeBytes / (1024 ** 3)).toFixed(1) : null;
  const resolution = videoStream?.Width ?? 0;
  const imgTag = item.ImageTags?.Primary;
  const backdropTag = item.BackdropImageTags?.[0];
  const poster = imgTag ? `/jellyfin/Items/${item.Id}/Images/Primary?maxHeight=600&tag=${imgTag}` : null;
  const backdrop = backdropTag ? `/jellyfin/Items/${item.Id}/Images/Backdrop?maxWidth=1280&tag=${backdropTag}` : null;
  const title = item.Name ?? 'Unknown';
  const runtimeMinutes = item.RunTimeTicks ? Math.round(item.RunTimeTicks / 10_000_000 / 60) : null;
  const overviewIsLong = (item.Overview?.length ?? 0) > 300;

  const handleDelete = () => {
    deleteMutation.mutate(item.Id, {
      onSuccess: () => {
        toast(`Deleted "${title}"`, 'success');
        navigate('/library');
      },
      onError: () => {
        toast('Failed to delete item', 'error');
      },
    });
    setShowDeleteModal(false);
  };

  const handleRedownload = () => {
    navigate(`/search?q=${encodeURIComponent(title)}`);
  };

  const jellyfinUrl = `/jellyfin/web/index.html#!/details?id=${item.Id}`;

  return (
    <div className="pb-6">
      {/* Backdrop */}
      {backdrop && (
        <div className="relative h-[300px] md:h-[400px] overflow-hidden">
          <img src={backdrop} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-bg-primary via-bg-primary/60 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-r from-bg-primary/80 to-transparent" />
        </div>
      )}

      <div className="px-4 md:px-8 -mt-24 relative z-10">
        <button onClick={() => navigate('/library')} className="mb-4 text-text-secondary hover:text-text-primary text-sm flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" /> Library
        </button>

        <div className="flex gap-6 flex-col md:flex-row">
          {/* Poster */}
          <div className="shrink-0 w-44 md:w-56">
            {poster ? (
              <img src={poster} alt={title} className="w-full rounded-xl shadow-2xl border border-white/10" />
            ) : (
              <div className="w-full aspect-[2/3] rounded-xl bg-bg-tertiary flex items-center justify-center text-text-tertiary border border-white/10">
                No Poster
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl md:text-3xl font-bold">{title}</h1>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              {item.ProductionYear && (
                <span className="text-sm text-text-secondary">{item.ProductionYear}</span>
              )}
              {resolution > 0 && <ResolutionBadge width={resolution} />}
              {item.CommunityRating != null && (
                <span className="text-sm text-text-secondary flex items-center gap-1">
                  <Star className="h-3.5 w-3.5 text-yellow-400 fill-yellow-400" /> {item.CommunityRating.toFixed(1)}
                </span>
              )}
              {runtimeMinutes != null && (
                <span className="text-sm text-text-secondary flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" /> {runtimeMinutes} min
                </span>
              )}
              {sizeGb && (
                <span className="text-sm text-text-secondary flex items-center gap-1">
                  <HardDrive className="h-3.5 w-3.5" /> {sizeGb} GB
                </span>
              )}
              {item.OfficialRating && (
                <span className="px-2 py-0.5 rounded border border-white/10 text-xs text-text-secondary">
                  {item.OfficialRating}
                </span>
              )}
            </div>

            {/* Genres as pills */}
            {item.Genres?.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {item.Genres.map((genre: string) => (
                  <GenrePill key={genre} genre={genre} />
                ))}
              </div>
            )}

            {/* Overview with Read More */}
            {item.Overview && (
              <div className="mt-4">
                <p className={`text-sm text-text-secondary leading-relaxed ${
                  !overviewExpanded && overviewIsLong ? 'line-clamp-4' : ''
                }`}>
                  {item.Overview}
                </p>
                {overviewIsLong && (
                  <button
                    onClick={() => setOverviewExpanded(!overviewExpanded)}
                    className="text-xs text-accent mt-1 hover:underline"
                  >
                    {overviewExpanded ? 'Show less' : 'Read more'}
                  </button>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-3 mt-6">
              <a href={jellyfinUrl} target="_blank" rel="noopener noreferrer">
                <Button size="lg">
                  <Play className="h-4 w-4" /> Play
                </Button>
              </a>
              <Button variant="secondary" onClick={handleRedownload}>
                <RefreshCw className="h-4 w-4" /> Re-download
              </Button>
              <Button variant="secondary" onClick={() => setShowDeleteModal(true)}>
                <Trash2 className="h-4 w-4" /> Delete
              </Button>
            </div>

            {/* File details — grid with labeled rows */}
            {mediaSource && (
              <div className="mt-6 p-4 rounded-xl bg-bg-secondary border border-white/5">
                <h3 className="text-sm font-medium mb-3">File Details</h3>
                <div className="space-y-0">
                  {videoStream?.DisplayTitle && (
                    <FileDetailRow label="Video" value={videoStream.DisplayTitle} />
                  )}
                  {audioStream?.DisplayTitle && (
                    <FileDetailRow label="Audio" value={audioStream.DisplayTitle} />
                  )}
                  {subtitleStream?.DisplayTitle && (
                    <FileDetailRow label="Subtitles" value={subtitleStream.DisplayTitle} />
                  )}
                  {mediaSource.Container && (
                    <FileDetailRow label="Container" value={mediaSource.Container.toUpperCase()} />
                  )}
                  {videoStream?.Width && videoStream?.Height && (
                    <FileDetailRow label="Resolution" value={`${videoStream.Width} x ${videoStream.Height}`} />
                  )}
                  {mediaSource.Bitrate && (
                    <FileDetailRow label="Bitrate" value={`${(mediaSource.Bitrate / 1_000_000).toFixed(1)} Mbps`} />
                  )}
                  {sizeGb && (
                    <FileDetailRow label="Size" value={`${sizeGb} GB`} />
                  )}
                  {mediaSource.Path && (
                    <FileDetailRow label="Path" value={mediaSource.Path.split('/').pop() ?? mediaSource.Path} />
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Delete confirmation */}
      <Modal open={showDeleteModal} onClose={() => setShowDeleteModal(false)} title="Delete Item">
        <p className="text-sm text-text-secondary mb-4">
          Are you sure you want to delete "{title}"? This will remove the file from disk and cannot be undone.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>Cancel</Button>
          <Button onClick={handleDelete} loading={deleteMutation.isPending}>
            <Trash2 className="h-4 w-4" /> Delete
          </Button>
        </div>
      </Modal>
    </div>
  );
}

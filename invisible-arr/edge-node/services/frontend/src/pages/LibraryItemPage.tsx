import { useParams, useNavigate } from 'react-router-dom';
import { useJellyfinItem, useDeleteJellyfinItem } from '@/hooks/useMedia';
import { FullSpinner } from '@/components/ui/Spinner';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { toast } from '@/components/ui/Toast';
import { ArrowLeft, Play, Trash2, RefreshCw, HardDrive } from 'lucide-react';
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

export function LibraryItemPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: item, isLoading } = useJellyfinItem(id!);
  const deleteMutation = useDeleteJellyfinItem();
  const [showDeleteModal, setShowDeleteModal] = useState(false);

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
  const sizeBytes = mediaSource?.Size ?? 0;
  const sizeGb = sizeBytes > 0 ? (sizeBytes / (1024 ** 3)).toFixed(1) : null;
  const resolution = videoStream?.Width ?? 0;
  const imgTag = item.ImageTags?.Primary;
  const backdropTag = item.BackdropImageTags?.[0];
  const poster = imgTag ? `/jellyfin/Items/${item.Id}/Images/Primary?maxHeight=600&tag=${imgTag}` : null;
  const backdrop = backdropTag ? `/jellyfin/Items/${item.Id}/Images/Backdrop?maxWidth=1280&tag=${backdropTag}` : null;
  const mediaType = item.Type === 'Movie' ? 'movie' : 'tv';
  const title = item.Name ?? 'Unknown';

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
        <div className="relative h-48 md:h-72 overflow-hidden">
          <img src={backdrop} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-bg-primary via-bg-primary/60 to-transparent" />
        </div>
      )}

      <div className="px-4 md:px-8 -mt-20 relative z-10">
        <button onClick={() => navigate('/library')} className="mb-4 text-text-secondary hover:text-text-primary text-sm flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" /> Library
        </button>

        <div className="flex gap-6 flex-col md:flex-row">
          {/* Poster */}
          <div className="shrink-0 w-40 md:w-52">
            {poster ? (
              <img src={poster} alt={title} className="w-full rounded-xl shadow-lg" />
            ) : (
              <div className="w-full aspect-[2/3] rounded-xl bg-bg-tertiary flex items-center justify-center text-text-tertiary">
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

            {item.Genres?.length > 0 && (
              <p className="text-xs text-text-tertiary mt-2">{item.Genres.join(' · ')}</p>
            )}

            {item.Overview && (
              <p className="text-sm text-text-secondary mt-4 leading-relaxed line-clamp-4 md:line-clamp-none">
                {item.Overview}
              </p>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-3 mt-6">
              <a href={jellyfinUrl} target="_blank" rel="noopener noreferrer">
                <Button size="lg">
                  <Play className="h-4 w-4" /> Play on Jellyfin
                </Button>
              </a>
              <Button variant="secondary" onClick={handleRedownload}>
                <RefreshCw className="h-4 w-4" /> Re-download
              </Button>
              <Button variant="secondary" onClick={() => setShowDeleteModal(true)}>
                <Trash2 className="h-4 w-4" /> Delete
              </Button>
            </div>

            {/* Media details */}
            {mediaSource && (
              <div className="mt-6 p-4 rounded-xl bg-bg-secondary border border-white/5">
                <h3 className="text-sm font-medium mb-2">File Details</h3>
                <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                  {videoStream?.DisplayTitle && <div>Video: {videoStream.DisplayTitle}</div>}
                  {mediaSource.MediaStreams?.find((s: any) => s.Type === 'Audio')?.DisplayTitle && (
                    <div>Audio: {mediaSource.MediaStreams.find((s: any) => s.Type === 'Audio').DisplayTitle}</div>
                  )}
                  {mediaSource.Container && <div>Container: {mediaSource.Container.toUpperCase()}</div>}
                  {sizeGb && <div>Size: {sizeGb} GB</div>}
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

import { X, Film } from 'lucide-react';

interface TrailerPlayerProps {
  videos?: { results?: { key: string; site: string; type: string; name: string; official: boolean }[] };
  onClose: () => void;
}

export function TrailerPlayer({ videos, onClose }: TrailerPlayerProps) {
  const trailers = videos?.results?.filter(
    (v) => v.site === 'YouTube' && v.type === 'Trailer',
  ) ?? [];

  // Prefer official trailers, fall back to any trailer
  const trailer = trailers.find((t) => t.official) ?? trailers[0] ?? null;

  if (!trailer) {
    return (
      <div className="relative glass rounded-xl p-8 mb-6 flex flex-col items-center justify-center gap-3">
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1.5 rounded-lg bg-bg-tertiary hover:bg-white/10 transition-colors"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
        <Film className="h-10 w-10 text-text-tertiary" />
        <p className="text-sm text-text-secondary">No trailer available</p>
      </div>
    );
  }

  return (
    <div className="relative mb-6">
      <div className="aspect-video rounded-xl overflow-hidden">
        <iframe
          src={`https://www.youtube-nocookie.com/embed/${trailer.key}?autoplay=1`}
          title={trailer.name}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full h-full"
        />
      </div>
      <button
        onClick={onClose}
        className="absolute top-3 right-3 p-1.5 rounded-lg bg-black/60 hover:bg-black/80 transition-colors z-10"
        aria-label="Close trailer"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

import { useParams } from 'react-router-dom';
import { useTMDBDetail } from '@/hooks/useMedia';
import { MediaDetail } from '@/components/media/MediaDetail';
import { FullSpinner } from '@/components/ui/Spinner';

export function MediaDetailPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const mediaType = (type === 'tv' ? 'tv' : 'movie') as 'movie' | 'tv';
  const { data, isLoading, isError } = useTMDBDetail(mediaType, Number(id));

  if (isLoading) return <FullSpinner />;
  if (isError || !data) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-text-secondary">Failed to load media details.</p>
      </div>
    );
  }

  return <MediaDetail detail={data} type={mediaType} />;
}

import { MediaCard } from './MediaCard';
import type { TMDBResult } from '@/api/media';

interface Props {
  items: TMDBResult[];
  className?: string;
}

export function MediaGrid({ items, className = '' }: Props) {
  return (
    <div className={`grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 ${className}`}>
      {items.map((item) => (
        <MediaCard key={`${item.media_type ?? 'x'}-${item.id}`} item={item} />
      ))}
    </div>
  );
}

export function MediaRow({ title, items }: { title: string; items: TMDBResult[] }) {
  if (!items.length) return null;
  return (
    <section className="mb-8">
      <h2 className="text-lg font-semibold mb-3 px-1">{title}</h2>
      <div className="scroll-row">
        {items.map((item) => (
          <MediaCard key={`${item.media_type ?? 'x'}-${item.id}`} item={item} className="w-[140px] sm:w-[160px]" />
        ))}
      </div>
    </section>
  );
}

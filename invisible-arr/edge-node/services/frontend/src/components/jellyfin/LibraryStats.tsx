import { Card } from '@/components/ui/Card';
import { useLibraryCounts } from '@/hooks/useAdmin';
import { Film, Tv } from 'lucide-react';

export function LibraryStats() {
  const { data } = useLibraryCounts();

  return (
    <Card className="p-4">
      <h3 className="font-semibold mb-3">Library</h3>
      <div className="grid grid-cols-2 gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-accent/10"><Film className="h-5 w-5 text-accent" /></div>
          <div>
            <p className="text-xl font-bold">{data?.movies ?? '—'}</p>
            <p className="text-xs text-text-secondary">Movies</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-accent/10"><Tv className="h-5 w-5 text-accent" /></div>
          <div>
            <p className="text-xl font-bold">{data?.shows ?? '—'}</p>
            <p className="text-xs text-text-secondary">TV Shows</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

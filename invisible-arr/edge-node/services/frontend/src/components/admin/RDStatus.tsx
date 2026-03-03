import { Card } from '@/components/ui/Card';
import { useRDStatus } from '@/hooks/useAdmin';
import { Zap } from 'lucide-react';

export function RDStatus() {
  const { data, isLoading, isError } = useRDStatus();

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Zap className="h-5 w-5 text-accent" />
        <h3 className="font-semibold">Real-Debrid</h3>
      </div>

      {isLoading ? (
        <p className="text-sm text-text-secondary">Checking...</p>
      ) : isError || !data?.enabled ? (
        <p className="text-sm text-text-secondary">Real-Debrid is not configured.</p>
      ) : (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-text-secondary">Account</span>
            <span>{data.username ?? '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Plan</span>
            <span>{data.type ?? '—'}</span>
          </div>
          {data.expiration && (
            <div className="flex justify-between">
              <span className="text-text-secondary">Expires</span>
              <span>{new Date(data.expiration).toLocaleDateString()}</span>
            </div>
          )}
          {data.points != null && (
            <div className="flex justify-between">
              <span className="text-text-secondary">Points</span>
              <span>{data.points}</span>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

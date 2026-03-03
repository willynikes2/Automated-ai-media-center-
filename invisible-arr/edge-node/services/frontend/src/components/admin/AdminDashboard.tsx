import { Activity, Users, HardDrive, Film, CheckCircle, XCircle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useSystemHealth, useJellyfinInfo, useLibraryCounts } from '@/hooks/useAdmin';
import { useJobs } from '@/hooks/useJobs';

function StatCard({ icon: Icon, label, value, sub }: { icon: React.ElementType; label: string; value: string | number; sub?: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-accent/10">
          <Icon className="h-5 w-5 text-accent" />
        </div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-xs text-text-secondary">{label}</p>
          {sub && <p className="text-xs text-text-tertiary mt-0.5">{sub}</p>}
        </div>
      </div>
    </Card>
  );
}

export function AdminDashboard() {
  const { data: health } = useSystemHealth();
  const { data: jfInfo } = useJellyfinInfo();
  const { data: counts } = useLibraryCounts();
  const { data: jobs } = useJobs({ limit: 100 });

  const activeJobs = jobs?.filter((j) => !['DONE', 'FAILED'].includes(j.state)).length ?? 0;
  const totalJobs = jobs?.length ?? 0;

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Activity} label="Active Jobs" value={activeJobs} sub={`${totalJobs} total`} />
        <StatCard icon={Film} label="Movies" value={counts?.movies ?? '—'} />
        <StatCard icon={Film} label="TV Shows" value={counts?.shows ?? '—'} />
        <StatCard icon={HardDrive} label="Jellyfin" value={jfInfo?.Version ?? '—'} sub={jfInfo?.OperatingSystem} />
      </div>

      {/* Service Health */}
      <Card className="p-4">
        <h3 className="font-semibold mb-3">Service Health</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { name: 'Agent API', ok: health?.status === 'ok' },
            { name: 'Database', ok: health?.db === 'ok' },
            { name: 'Redis', ok: health?.redis === 'ok' },
            { name: 'Jellyfin', ok: !!jfInfo?.Version },
          ].map((svc) => (
            <div key={svc.name} className="flex items-center gap-2 text-sm">
              {svc.ok ? (
                <CheckCircle className="h-4 w-4 text-status-available" />
              ) : (
                <XCircle className="h-4 w-4 text-status-failed" />
              )}
              <span className={svc.ok ? 'text-text-primary' : 'text-status-failed'}>{svc.name}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

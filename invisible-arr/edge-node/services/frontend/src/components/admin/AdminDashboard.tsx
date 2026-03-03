import { Activity, Users, HardDrive, CheckCircle, XCircle, Zap } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { StateBadge } from '@/components/ui/Badge';
import { useSystemHealth, useJellyfinInfo, useAdminStats, useRDStatus, useAllJobs } from '@/hooks/useAdmin';
import type { Job } from '@/api/jobs';

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

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function AdminDashboard() {
  const { data: stats } = useAdminStats();
  const { data: health } = useSystemHealth();
  const { data: jfInfo } = useJellyfinInfo();
  const { data: rdStatus } = useRDStatus();
  const { data: recentJobs } = useAllJobs({ limit: 10 });

  const storageStr = stats?.storage_used_gb != null ? `${stats.storage_used_gb.toFixed(1)} GB` : '--';

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Users} label="Total Users" value={stats?.total_users ?? '--'} />
        <StatCard icon={Users} label="Active Users" value={stats?.active_users ?? '--'} />
        <StatCard icon={Activity} label="Total Jobs" value={stats?.total_jobs ?? '--'} />
        <StatCard icon={HardDrive} label="Storage Used" value={storageStr} />
      </div>

      {/* Jobs by state */}
      {stats?.jobs_by_state && Object.keys(stats.jobs_by_state).length > 0 && (
        <Card className="p-4">
          <h3 className="font-semibold mb-3">Jobs by State</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.jobs_by_state).map(([state, count]) => (
              <div key={state} className="flex items-center gap-1.5">
                <StateBadge state={state} />
                <span className="text-sm font-medium text-text-secondary">{count}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* RD Status summary */}
      {rdStatus?.enabled && (
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="h-4 w-4 text-accent" />
            <h3 className="font-semibold text-sm">Real-Debrid</h3>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {rdStatus.username && (
              <div>
                <span className="text-text-secondary">Account: </span>
                <span>{rdStatus.username}</span>
              </div>
            )}
            {rdStatus.type && (
              <div>
                <span className="text-text-secondary">Plan: </span>
                <span>{rdStatus.type}</span>
              </div>
            )}
            {rdStatus.expiration && (
              <div>
                <span className="text-text-secondary">Expires: </span>
                <span>{new Date(rdStatus.expiration).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Recent activity */}
      <Card className="p-4">
        <h3 className="font-semibold mb-3">Recent Activity</h3>
        {!recentJobs?.length ? (
          <p className="text-sm text-text-secondary">No recent jobs.</p>
        ) : (
          <div className="space-y-2">
            {(recentJobs as Job[]).slice(0, 5).map((job) => (
              <div key={job.id} className="flex items-center justify-between p-2 rounded-lg bg-bg-tertiary/30">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-sm font-medium truncate">{job.title}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <StateBadge state={job.state} />
                  <span className="text-xs text-text-tertiary whitespace-nowrap">{timeAgo(job.updated_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Service Health */}
      <Card className="p-4">
        <h3 className="font-semibold mb-3">Service Health</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { name: 'Agent API', ok: health?.status === 'ok' },
            { name: 'Database', ok: health?.db === 'ok' },
            { name: 'Redis', ok: health?.redis === 'ok' },
            { name: 'Media Server', ok: !!jfInfo?.Version },
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

import { useState } from 'react';
import { useJobs, filterActive, filterCompleted, filterMonitored, filterIssues, useRetryJob, useCancelJob, useJobProgress } from '@/hooks/useJobs';
import { JobTimeline } from '@/components/jobs/JobTimeline';
import { StateBadge, Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { FullSpinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { toast } from '@/components/ui/Toast';
import { Activity, CheckCircle, XCircle, RefreshCw, Ban, Cloud, HardDrive, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Job } from '@/api/jobs';

type Filter = 'all' | 'active' | 'monitored' | 'done' | 'issues';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'monitored', label: 'Waiting' },
  { key: 'done', label: 'Complete' },
  { key: 'issues', label: 'Issues' },
];

function AcquisitionBadge({ mode, method }: { mode: string; method?: string | null }) {
  if (method === 'usenet' || method === 'sabnzbd') {
    return (
      <Badge className="bg-blue-500/20 text-blue-400">
        <HardDrive className="h-3 w-3 mr-1" />
        Usenet
      </Badge>
    );
  }
  return (
    <Badge className="bg-emerald-500/20 text-emerald-400">
      <Cloud className="h-3 w-3 mr-1" />
      Real-Debrid
    </Badge>
  );
}

function ActiveJobCard({ job }: { job: Job }) {
  const cancelMutation = useCancelJob();
  const isDownloading = ['DOWNLOADING', 'IMPORTING', 'ACQUIRING'].includes(job.state);
  const { data: progressData } = useJobProgress(job.id, isDownloading);
  const progress = progressData?.percent ?? -1;

  const handleCancel = (e: React.MouseEvent) => {
    e.preventDefault();
    cancelMutation.mutate(job.id, {
      onSuccess: () => toast('Job cancelled', 'success'),
      onError: () => toast('Failed to cancel', 'error'),
    });
  };

  return (
    <Card className="p-4 ring-1 ring-accent/10">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0 flex-1">
          <Link to={`/requests/${job.id}`} className="font-medium text-sm hover:text-accent transition-colors">
            {job.title}
          </Link>
          <p className="text-xs text-text-tertiary mt-0.5">
            {job.media_type === 'tv' ? 'TV Show' : 'Movie'}
            {job.season != null && ` · S${String(job.season).padStart(2, '0')}`}
            {job.episode != null && `E${String(job.episode).padStart(2, '0')}`}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <AcquisitionBadge mode={job.acquisition_mode} method={job.acquisition_method} />
          <StateBadge state={job.state} />
        </div>
      </div>

      <JobTimeline currentState={job.state} progress={progress >= 0 ? progress : undefined} progressData={progressData} />

      {job.selected_candidate && (
        <div className="mt-3 pt-3 border-t border-white/5 text-xs text-text-secondary">
          <span className="truncate block">{job.selected_candidate.title}</span>
          <span className="text-text-tertiary">
            {job.selected_candidate.resolution && `${job.selected_candidate.resolution}p`}
            {job.selected_candidate.size_gb && ` · ${job.selected_candidate.size_gb.toFixed(1)} GB`}
            {job.selected_candidate.source && ` · ${job.selected_candidate.source}`}
          </span>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between">
        {job.retry_count > 0 && (
          <div className="flex items-center gap-1 text-xs text-yellow-400">
            <RefreshCw className="h-3 w-3" />
            Retry #{job.retry_count}
          </div>
        )}
        <div className="flex items-center gap-2 ml-auto">
          <button
            onClick={handleCancel}
            disabled={cancelMutation.isPending}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-50"
          >
            <Ban className="h-3 w-3" />
            Cancel
          </button>
        </div>
      </div>
    </Card>
  );
}

function friendlyError(raw: string | null): string | null {
  if (!raw) return null;
  // New diagnostic messages are already mom-friendly, just pass through
  // Keep fallbacks for old-format messages still in DB
  if (raw.includes('did not grab a release')) return 'No downloads found yet';
  if (raw.includes('import not confirmed')) return 'Downloaded but still organizing';
  if (raw.includes('announced but not released')) return 'Waiting for release';
  if (raw.includes('in cinemas only')) return 'Waiting for digital release';
  if (raw.includes('not aired yet')) return 'Waiting to air';
  return raw.length > 60 ? raw.slice(0, 60) + '...' : raw;
}

function CompletedRow({ job }: { job: Job }) {
  const isIssue = ['FAILED', 'INVESTIGATING', 'UNAVAILABLE'].includes(job.state);
  const retryMutation = useRetryJob();

  const handleRetry = (e: React.MouseEvent) => {
    e.preventDefault();
    retryMutation.mutate(job.id, {
      onSuccess: () => toast('Job queued for retry', 'success'),
      onError: () => toast('Failed to retry', 'error'),
    });
  };

  return (
    <Link
      to={`/requests/${job.id}`}
      className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-bg-secondary/50 transition-colors"
    >
      {isIssue ? (
        <XCircle className="h-4 w-4 text-status-failed shrink-0" />
      ) : (
        <CheckCircle className="h-4 w-4 text-status-available shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{job.title}</p>
        <p className="text-[10px] text-text-tertiary">
          {job.media_type === 'tv' ? 'TV' : 'Movie'}
          {' · '}
          {new Date(job.updated_at).toLocaleDateString()}
          {isIssue && job.last_error && (
            <span className="text-status-failed"> · {friendlyError(job.last_error)}</span>
          )}
          {isIssue && !job.last_error && job.retry_count > 0 && ` · ${job.retry_count} retries`}
        </p>
      </div>
      <AcquisitionBadge mode={job.acquisition_mode} method={job.acquisition_method} />
      {job.selected_candidate?.resolution && (
        <span className="text-xs text-text-tertiary shrink-0">{job.selected_candidate.resolution}p</span>
      )}
      {isIssue ? (
        <button
          onClick={handleRetry}
          className="shrink-0 text-xs px-2 py-1 rounded bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
        >
          Retry
        </button>
      ) : job.imported_path ? (
        <span className="text-xs text-status-available shrink-0">Imported</span>
      ) : null}
      <StateBadge state={job.state} />
    </Link>
  );
}

export function ActivityPage() {
  const { data: jobs, isLoading } = useJobs({ limit: 100 });
  const [filter, setFilter] = useState<Filter>('all');

  if (isLoading) return <FullSpinner />;

  const active = filterActive(jobs);
  const completed = filterCompleted(jobs);
  const monitored = filterMonitored(jobs);
  const issues = filterIssues(jobs);
  const done = (jobs ?? []).filter((j) => j.state === 'DONE');

  const counts: Record<Filter, number> = {
    all: (jobs ?? []).length,
    active: active.length,
    monitored: monitored.length,
    done: done.length,
    issues: issues.length,
  };

  const showActive = filter === 'all' || filter === 'active';
  const showMonitored = filter === 'all' || filter === 'monitored';
  const showCompleted = filter === 'all' || filter === 'done';
  const showIssues = filter === 'issues';

  return (
    <div className="px-4 md:px-8 py-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Activity</h1>
        <p className="text-sm text-text-secondary">Real-time download progress and history.</p>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              filter === f.key ? 'bg-accent text-white' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {f.label} {counts[f.key] > 0 && <span className="ml-1 text-xs opacity-70">({counts[f.key]})</span>}
          </button>
        ))}
      </div>

      {/* Active downloads */}
      {showActive && active.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Active ({active.length})
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {active.map((job) => (
              <ActiveJobCard key={job.id} job={job} />
            ))}
          </div>
        </section>
      )}

      {showActive && active.length === 0 && filter === 'active' && (
        <Card className="p-6 text-center">
          <Activity className="h-8 w-8 mx-auto text-text-tertiary mb-2" />
          <p className="text-sm text-text-secondary">No active downloads</p>
        </Card>
      )}

      {/* Waiting for release */}
      {showMonitored && monitored.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Waiting for Release ({monitored.length})
          </h2>
          <Card className="divide-y divide-white/5">
            {monitored.map((job) => (
              <Link
                key={job.id}
                to={`/requests/${job.id}`}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-bg-secondary/50 transition-colors"
              >
                <Clock className="h-4 w-4 text-amber-400 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{job.title}</p>
                  <p className="text-[10px] text-text-tertiary">
                    {job.media_type === 'tv' ? 'TV' : 'Movie'}
                    {' · '}
                    Auto-downloads when available
                  </p>
                </div>
                <StateBadge state={job.state} />
              </Link>
            ))}
          </Card>
        </section>
      )}

      {showMonitored && monitored.length === 0 && filter === 'monitored' && (
        <Card className="p-6 text-center">
          <Clock className="h-8 w-8 mx-auto text-text-tertiary mb-2" />
          <p className="text-sm text-text-secondary">No items waiting for release</p>
        </Card>
      )}

      {/* Issues */}
      {showIssues && (
        <section>
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Issues ({issues.length})
          </h2>
          {issues.length > 0 ? (
            <Card className="divide-y divide-white/5">
              {issues.map((job) => (
                <CompletedRow key={job.id} job={job} />
              ))}
            </Card>
          ) : (
            <Card className="p-6 text-center">
              <p className="text-sm text-text-secondary">No issues</p>
            </Card>
          )}
        </section>
      )}

      {/* Completed history */}
      {showCompleted && done.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Complete ({done.length})
          </h2>
          <Card className="divide-y divide-white/5">
            {done.map((job) => (
              <CompletedRow key={job.id} job={job} />
            ))}
          </Card>
        </section>
      )}

      {/* All history (when "all" filter) */}
      {filter === 'all' && active.length === 0 && completed.length === 0 && (
        <Card className="p-6 text-center">
          <Activity className="h-8 w-8 mx-auto text-text-tertiary mb-2" />
          <p className="text-sm text-text-secondary">No activity yet</p>
          <p className="text-xs text-text-tertiary mt-1">Request something from Discover to get started.</p>
        </Card>
      )}
    </div>
  );
}

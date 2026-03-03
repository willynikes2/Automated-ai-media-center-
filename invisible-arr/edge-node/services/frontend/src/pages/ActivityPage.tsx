import { useJobs, filterActive, filterCompleted } from '@/hooks/useJobs';
import { JobTimeline } from '@/components/jobs/JobTimeline';
import { StateBadge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { FullSpinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Activity, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Job } from '@/api/jobs';

function ActiveJobCard({ job }: { job: Job }) {
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
        <StateBadge state={job.state} />
      </div>

      {/* Mini pipeline */}
      <JobTimeline currentState={job.state} />

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

      {job.retry_count > 0 && (
        <div className="mt-2 flex items-center gap-1 text-xs text-yellow-400">
          <RefreshCw className="h-3 w-3" />
          Retry #{job.retry_count}
        </div>
      )}
    </Card>
  );
}

function CompletedRow({ job }: { job: Job }) {
  const isFailed = job.state === 'FAILED';
  return (
    <Link
      to={`/requests/${job.id}`}
      className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-bg-secondary/50 transition-colors"
    >
      {isFailed ? (
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
          {isFailed && job.retry_count > 0 && ` · ${job.retry_count} retries`}
        </p>
      </div>
      {job.selected_candidate?.resolution && (
        <span className="text-xs text-text-tertiary shrink-0">{job.selected_candidate.resolution}p</span>
      )}
      {job.imported_path && (
        <span className="text-xs text-status-available shrink-0">Imported</span>
      )}
      <StateBadge state={job.state} />
    </Link>
  );
}

export function ActivityPage() {
  const { data: jobs, isLoading } = useJobs({ limit: 100 });

  if (isLoading) return <FullSpinner />;

  const active = filterActive(jobs);
  const completed = filterCompleted(jobs);

  return (
    <div className="px-4 md:px-8 py-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold mb-1">Activity</h1>
        <p className="text-sm text-text-secondary">Real-time download progress and history.</p>
      </div>

      {/* Active downloads */}
      {active.length > 0 ? (
        <section>
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Active ({active.length})
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {active.map((job) => (
              <ActiveJobCard key={job.id} job={job} />
            ))}
          </div>
        </section>
      ) : (
        <Card className="p-6 text-center">
          <Activity className="h-8 w-8 mx-auto text-text-tertiary mb-2" />
          <p className="text-sm text-text-secondary">No active downloads</p>
          <p className="text-xs text-text-tertiary mt-1">Request something from Discover to get started.</p>
        </Card>
      )}

      {/* History */}
      {completed.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
            History ({completed.length})
          </h2>
          <Card className="divide-y divide-white/5">
            {completed.map((job) => (
              <CompletedRow key={job.id} job={job} />
            ))}
          </Card>
        </section>
      )}
    </div>
  );
}

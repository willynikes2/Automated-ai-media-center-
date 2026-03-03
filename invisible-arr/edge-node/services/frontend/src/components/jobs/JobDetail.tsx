import { StateBadge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { JobTimeline } from './JobTimeline';
import { useRetryJob } from '@/hooks/useJobs';
import { toast } from '@/components/ui/Toast';
import { RefreshCw } from 'lucide-react';
import type { JobDetail as JobDetailType } from '@/api/jobs';

const FRIENDLY_ERRORS: Record<string, string> = {
  'Unhandled exception during processing': 'Something went wrong while processing this request. It may work on retry.',
  'Prowlarr search failed': 'Could not search for releases. The indexer may be temporarily down.',
  'No candidates found': 'No suitable releases were found matching your quality preferences.',
  'RD magnet error': 'Real-Debrid could not process this torrent. Try a different release or downloader.',
};

function friendlyError(message: string): string {
  return FRIENDLY_ERRORS[message] ?? message;
}

export function JobDetailView({ job }: { job: JobDetailType }) {
  const retryMutation = useRetryJob();

  const handleRetry = () => {
    retryMutation.mutate(job.id, {
      onSuccess: () => toast('Job queued for retry', 'success'),
      onError: () => toast('Failed to retry job', 'error'),
    });
  };

  const lastErrorMessage = job.events?.length > 0 ? job.events[job.events.length - 1].message : '';

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 className="text-xl font-bold">{job.title}</h2>
          <StateBadge state={job.state} />
        </div>
        <p className="text-sm text-text-secondary">
          {job.media_type === 'tv' ? 'TV Show' : 'Movie'}
          {job.season != null && ` · Season ${job.season}`}
          {job.episode != null && `, Episode ${job.episode}`}
          {' · '}
          Requested {new Date(job.created_at).toLocaleDateString()}
        </p>
      </div>

      {/* Pipeline */}
      <Card className="p-4">
        <JobTimeline currentState={job.state} events={job.events} />
      </Card>

      {/* Selected release */}
      {job.selected_candidate && (
        <Card className="p-4">
          <h3 className="text-sm font-medium mb-2">Selected Release</h3>
          <p className="text-sm text-text-secondary">{job.selected_candidate.title}</p>
          <div className="flex flex-wrap gap-4 mt-2 text-xs text-text-tertiary">
            {job.selected_candidate.resolution && <span>{job.selected_candidate.resolution}p</span>}
            {job.selected_candidate.source && <span>{job.selected_candidate.source}</span>}
            {job.selected_candidate.codec && <span>{job.selected_candidate.codec}</span>}
            {job.selected_candidate.size_gb && <span>{job.selected_candidate.size_gb.toFixed(2)} GB</span>}
            {job.selected_candidate.seeders != null && <span>{job.selected_candidate.seeders} seeders</span>}
          </div>
        </Card>
      )}

      {/* Imported path */}
      {job.imported_path && (
        <Card className="p-4">
          <h3 className="text-sm font-medium mb-1">Imported</h3>
          <p className="text-xs text-text-secondary font-mono truncate">{job.imported_path}</p>
        </Card>
      )}

      {/* Error */}
      {job.state === 'FAILED' && (
        <Card className="p-4 border-status-failed/20">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-medium text-status-failed mb-1">Download Failed</h3>
              <p className="text-sm text-text-secondary">
                {lastErrorMessage ? friendlyError(lastErrorMessage) : 'An unexpected error occurred.'}
              </p>
              {job.retry_count > 0 && (
                <p className="text-xs text-text-tertiary mt-1">
                  Attempted {job.retry_count} {job.retry_count === 1 ? 'retry' : 'retries'}
                </p>
              )}
            </div>
            <Button
              variant="secondary"
              onClick={handleRetry}
              loading={retryMutation.isPending}
            >
              <RefreshCw className="h-4 w-4" /> Retry
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

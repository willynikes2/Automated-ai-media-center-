import { StateBadge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { JobTimeline } from './JobTimeline';
import type { JobDetail as JobDetailType } from '@/api/jobs';

export function JobDetailView({ job }: { job: JobDetailType }) {
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
          <h3 className="text-sm font-medium text-status-failed mb-1">Failed</h3>
          <p className="text-sm text-text-secondary">
            Download failed{job.retry_count > 0 ? ` after ${job.retry_count} retries` : ''}.
            {job.events?.length > 0 && ` Last: ${job.events[job.events.length - 1].message}`}
          </p>
        </Card>
      )}
    </div>
  );
}

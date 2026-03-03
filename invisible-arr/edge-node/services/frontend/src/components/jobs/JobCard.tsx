import { Link } from 'react-router-dom';
import { StateBadge } from '@/components/ui/Badge';
import type { Job } from '@/api/jobs';

export function JobCard({ job }: { job: Job }) {
  const isActive = !['DONE', 'FAILED'].includes(job.state);

  return (
    <Link to={`/requests/${job.id}`} className="block">
      <div className={`bg-bg-secondary rounded-xl border border-white/5 p-4 hover:border-accent/20 transition-all ${isActive ? 'ring-1 ring-accent/10' : ''}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="font-medium text-sm truncate">{job.title}</h3>
            <p className="text-xs text-text-tertiary mt-0.5">
              {job.media_type === 'tv' ? 'TV Show' : 'Movie'}
              {job.season != null && ` · S${String(job.season).padStart(2, '0')}`}
              {job.episode != null && `E${String(job.episode).padStart(2, '0')}`}
            </p>
          </div>
          <StateBadge state={job.state} />
        </div>

        {job.selected_candidate && (
          <p className="text-xs text-text-secondary mt-2 truncate">
            {job.selected_candidate.title}
            {job.selected_candidate.resolution && ` · ${job.selected_candidate.resolution}p`}
            {job.selected_candidate.size_gb && ` · ${job.selected_candidate.size_gb.toFixed(1)} GB`}
          </p>
        )}

        {job.state === 'FAILED' && (
          <p className="text-xs text-status-failed mt-2 truncate">
            Failed{job.retry_count > 0 ? ` (${job.retry_count} retries)` : ''}
          </p>
        )}

        <p className="text-[10px] text-text-tertiary mt-2">
          {new Date(job.created_at).toLocaleDateString()}
        </p>
      </div>
    </Link>
  );
}

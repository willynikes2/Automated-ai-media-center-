import { JobCard } from './JobCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { Inbox } from 'lucide-react';
import type { Job } from '@/api/jobs';

export function JobList({ jobs, emptyMessage = 'No requests yet' }: { jobs: Job[]; emptyMessage?: string }) {
  if (!jobs.length) {
    return <EmptyState icon={Inbox} title={emptyMessage} description="Request something from Discover to get started." />;
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </div>
  );
}

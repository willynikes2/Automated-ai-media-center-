import { useParams } from 'react-router-dom';
import { useJobs, useJob, filterActive, filterCompleted } from '@/hooks/useJobs';
import { JobList } from '@/components/jobs/JobList';
import { JobDetailView } from '@/components/jobs/JobDetail';
import { FullSpinner } from '@/components/ui/Spinner';

export function RequestsPage() {
  const { id } = useParams<{ id?: string }>();

  if (id) return <RequestDetail id={id} />;
  return <RequestsList />;
}

function RequestsList() {
  const { data: jobs, isLoading } = useJobs({ limit: 100 });

  if (isLoading) return <FullSpinner />;

  const active = filterActive(jobs);
  const completed = filterCompleted(jobs);

  return (
    <div className="px-4 md:px-8 py-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold mb-1">My Requests</h1>
        <p className="text-sm text-text-secondary">Track and manage your media requests.</p>
      </div>

      {active.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Active ({active.length})</h2>
          <JobList jobs={active} />
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold mb-3">
          {active.length > 0 ? 'Completed' : 'All Requests'}
        </h2>
        <JobList jobs={active.length > 0 ? completed : (jobs ?? [])} emptyMessage="No requests yet" />
      </section>
    </div>
  );
}

function RequestDetail({ id }: { id: string }) {
  const { data: job, isLoading } = useJob(id);

  if (isLoading) return <FullSpinner />;
  if (!job) return <p className="p-8 text-text-secondary">Job not found.</p>;

  return (
    <div className="px-4 md:px-8 py-6 max-w-3xl">
      <JobDetailView job={job} />
    </div>
  );
}

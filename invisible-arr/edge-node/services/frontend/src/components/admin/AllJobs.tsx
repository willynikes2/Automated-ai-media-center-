import { JobList } from '@/components/jobs/JobList';
import { useAllJobs } from '@/hooks/useAdmin';
import { useState } from 'react';
import { Select } from '@/components/ui/Select';

export function AllJobs() {
  const [stateFilter, setStateFilter] = useState('');
  const { data: jobs, isLoading } = useAllJobs({ state: stateFilter || undefined, limit: 100 });

  return (
    <div>
      <div className="flex items-center gap-4 mb-4">
        <Select
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          options={[
            { value: '', label: 'All States' },
            { value: 'CREATED', label: 'Created' },
            { value: 'RESOLVING', label: 'Resolving' },
            { value: 'SEARCHING', label: 'Searching' },
            { value: 'SELECTED', label: 'Selected' },
            { value: 'ACQUIRING', label: 'Acquiring' },
            { value: 'IMPORTING', label: 'Importing' },
            { value: 'VERIFYING', label: 'Verifying' },
            { value: 'DONE', label: 'Done' },
            { value: 'FAILED', label: 'Failed' },
          ]}
        />
      </div>
      {isLoading ? (
        <p className="text-sm text-text-secondary">Loading...</p>
      ) : (
        <JobList jobs={jobs ?? []} emptyMessage="No jobs found" />
      )}
    </div>
  );
}

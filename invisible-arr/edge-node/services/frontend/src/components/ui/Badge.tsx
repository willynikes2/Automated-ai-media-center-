import type { JobState } from '@/api/jobs';

const stateColors: Record<string, string> = {
  CREATED: 'bg-text-tertiary/20 text-text-secondary',
  RESOLVING: 'bg-status-downloading/20 text-status-downloading',
  SEARCHING: 'bg-status-downloading/20 text-status-downloading',
  SELECTED: 'bg-yellow-500/20 text-yellow-400',
  ACQUIRING: 'bg-orange-500/20 text-orange-400',
  IMPORTING: 'bg-orange-500/20 text-orange-400',
  VERIFYING: 'bg-orange-500/20 text-orange-400',
  DONE: 'bg-status-available/20 text-status-available',
  FAILED: 'bg-status-failed/20 text-status-failed',
};

export function Badge({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}

export function StateBadge({ state }: { state: JobState | string }) {
  return (
    <Badge className={stateColors[state] ?? 'bg-bg-tertiary text-text-secondary'}>
      {state}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: 'available' | 'requested' | 'processing' | 'unavailable' }) {
  const styles: Record<string, string> = {
    available: 'bg-status-available/20 text-status-available',
    requested: 'bg-status-requested/20 text-status-requested',
    processing: 'bg-status-processing/20 text-status-processing',
    unavailable: 'bg-bg-tertiary text-text-tertiary',
  };
  const labels: Record<string, string> = {
    available: 'Available',
    requested: 'Requested',
    processing: 'Processing',
    unavailable: 'Not Available',
  };
  return <Badge className={styles[status]}>{labels[status]}</Badge>;
}

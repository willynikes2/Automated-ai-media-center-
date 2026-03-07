import type { JobState } from '@/api/jobs';

const STATE_LABELS: Record<string, string> = {
  REQUESTED: 'Requested',
  SEARCHING: 'Searching',
  DOWNLOADING: 'Downloading',
  IMPORTING: 'Importing',
  AVAILABLE: 'Available',
  WAITING: 'Waiting for Release',
  FAILED: 'Failed',
  DELETED: 'Removed',
};

const stateColors: Record<string, string> = {
  REQUESTED: 'bg-blue-500/20 text-blue-400',
  SEARCHING: 'bg-yellow-500/20 text-yellow-400',
  DOWNLOADING: 'bg-purple-500/20 text-purple-400',
  IMPORTING: 'bg-indigo-500/20 text-indigo-400',
  AVAILABLE: 'bg-status-available/20 text-status-available',
  WAITING: 'bg-amber-500/20 text-amber-400',
  FAILED: 'bg-red-500/20 text-red-400',
  DELETED: 'bg-text-tertiary/20 text-text-tertiary',
};

const ACTIVE_STATES = ['REQUESTED', 'SEARCHING', 'DOWNLOADING', 'IMPORTING'];

export function Badge({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}

export function StateBadge({ state }: { state: JobState | string }) {
  const isActive = ACTIVE_STATES.includes(state);
  return (
    <Badge className={`${stateColors[state] ?? 'bg-bg-tertiary text-text-secondary'} ${isActive ? 'animate-pulse' : ''}`}>
      {STATE_LABELS[state] ?? state}
    </Badge>
  );
}

export function getStateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
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

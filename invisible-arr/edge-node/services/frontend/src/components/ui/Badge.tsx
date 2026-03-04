import type { JobState } from '@/api/jobs';

const STATE_LABELS: Record<string, string> = {
  CREATED: 'Queued',
  RESOLVING: 'Looking up info',
  ADDING: 'Adding to library',
  SEARCHING: 'Finding releases',
  SELECTED: 'Release found',
  ACQUIRING: 'Downloading',
  IMPORTING: 'Organizing files',
  VERIFYING: 'Checking quality',
  DONE: 'Complete',
  FAILED: 'Failed',
};

const stateColors: Record<string, string> = {
  CREATED: 'bg-text-tertiary/20 text-text-secondary',
  RESOLVING: 'bg-status-downloading/20 text-status-downloading',
  ADDING: 'bg-blue-500/20 text-blue-400',
  SEARCHING: 'bg-status-downloading/20 text-status-downloading',
  SELECTED: 'bg-yellow-500/20 text-yellow-400',
  ACQUIRING: 'bg-orange-500/20 text-orange-400',
  IMPORTING: 'bg-orange-500/20 text-orange-400',
  VERIFYING: 'bg-orange-500/20 text-orange-400',
  DONE: 'bg-status-available/20 text-status-available',
  FAILED: 'bg-status-failed/20 text-status-failed',
};

const ACTIVE_STATES = ['RESOLVING', 'ADDING', 'SEARCHING', 'ACQUIRING', 'IMPORTING', 'VERIFYING'];

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

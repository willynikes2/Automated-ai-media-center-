import type { JobState } from '@/api/jobs';

const STATE_LABELS: Record<string, string> = {
  CREATED: 'Queued',
  SEARCHING: 'Looking for best version',
  DOWNLOADING: 'Downloading',
  IMPORTING: 'Organizing files',
  VERIFYING: 'Checking quality',
  DONE: 'Ready to watch!',
  MONITORED: 'Waiting for Release',
  INVESTIGATING: 'Working on it',
  UNAVAILABLE: 'Not available',
  FAILED: 'Working on it',       // Map FAILED to friendly text (diagnostic engine handles it)
  DELETED: 'Removed',
  // Legacy states
  RESOLVING: 'Looking for best version',
  ADDING: 'Looking for best version',
  SELECTED: 'Found a version',
  ACQUIRING: 'Downloading',
};

const stateColors: Record<string, string> = {
  CREATED: 'bg-text-tertiary/20 text-text-secondary',
  SEARCHING: 'bg-blue-500/20 text-blue-400',
  DOWNLOADING: 'bg-orange-500/20 text-orange-400',
  IMPORTING: 'bg-orange-500/20 text-orange-400',
  VERIFYING: 'bg-orange-500/20 text-orange-400',
  DONE: 'bg-status-available/20 text-status-available',
  MONITORED: 'bg-amber-500/20 text-amber-400',
  INVESTIGATING: 'bg-yellow-500/20 text-yellow-400',
  UNAVAILABLE: 'bg-red-500/20 text-red-400',
  FAILED: 'bg-yellow-500/20 text-yellow-400',
  DELETED: 'bg-text-tertiary/20 text-text-tertiary',
  // Legacy
  RESOLVING: 'bg-blue-500/20 text-blue-400',
  ADDING: 'bg-blue-500/20 text-blue-400',
  SELECTED: 'bg-yellow-500/20 text-yellow-400',
  ACQUIRING: 'bg-orange-500/20 text-orange-400',
};

const ACTIVE_STATES = ['SEARCHING', 'DOWNLOADING', 'IMPORTING', 'VERIFYING', 'INVESTIGATING',
                       'RESOLVING', 'ADDING', 'ACQUIRING'];

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

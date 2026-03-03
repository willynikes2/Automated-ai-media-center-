import { Check, Circle, X } from 'lucide-react';
import type { JobState, JobEvent } from '@/api/jobs';

const PIPELINE: JobState[] = ['CREATED', 'RESOLVING', 'SEARCHING', 'SELECTED', 'ACQUIRING', 'IMPORTING', 'VERIFYING', 'DONE'];

function stateIndex(state: string): number {
  return PIPELINE.indexOf(state as JobState);
}

export function JobTimeline({ currentState, events }: { currentState: string; events?: JobEvent[] }) {
  const isFailed = currentState === 'FAILED';
  const currentIdx = isFailed ? -1 : stateIndex(currentState);

  return (
    <div className="space-y-6">
      {/* Pipeline steps */}
      <div className="flex items-center gap-1 overflow-x-auto pb-2">
        {PIPELINE.map((step, i) => {
          const done = currentIdx > i;
          const active = currentIdx === i;
          const failed = isFailed && i === 0; // show failure indicator

          return (
            <div key={step} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={`h-7 w-7 rounded-full flex items-center justify-center text-xs shrink-0 ${
                    done
                      ? 'bg-status-available text-white'
                      : active
                      ? 'bg-accent text-white ring-2 ring-accent/30'
                      : isFailed
                      ? 'bg-status-failed/20 text-status-failed'
                      : 'bg-bg-tertiary text-text-tertiary'
                  }`}
                >
                  {done ? <Check className="h-3.5 w-3.5" /> : isFailed && i <= 1 ? <X className="h-3.5 w-3.5" /> : <Circle className="h-3 w-3" />}
                </div>
                <span className={`text-[9px] mt-1 whitespace-nowrap ${active ? 'text-accent font-medium' : 'text-text-tertiary'}`}>
                  {step}
                </span>
              </div>
              {i < PIPELINE.length - 1 && (
                <div className={`h-0.5 w-6 mx-0.5 ${done ? 'bg-status-available' : 'bg-bg-tertiary'}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Event list */}
      {events && events.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider">Events</h4>
          <div className="space-y-1.5">
            {events.map((ev) => (
              <div key={ev.id} className="flex items-start gap-3 text-xs">
                <span className="text-text-tertiary whitespace-nowrap shrink-0">
                  {new Date(ev.created_at).toLocaleTimeString()}
                </span>
                <span className="font-medium text-text-primary">{ev.state}</span>
                {ev.message && <span className="text-text-secondary truncate">{ev.message}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

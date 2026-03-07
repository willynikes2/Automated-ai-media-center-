import { useState } from 'react';
import { useReleases, useGrabRelease } from '@/hooks/useJobs';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { toast } from '@/components/ui/Toast';
import { X, Download, ChevronDown } from 'lucide-react';
import type { Release } from '@/api/jobs';

function ProtocolBadge({ protocol }: { protocol: string }) {
  const styles: Record<string, string> = {
    Torrent: 'bg-orange-500/20 text-orange-400',
    Usenet: 'bg-blue-500/20 text-blue-400',
    RD: 'bg-emerald-500/20 text-emerald-400',
  };
  return <Badge className={styles[protocol] ?? 'bg-bg-tertiary text-text-secondary'}>{protocol}</Badge>;
}

function ReleaseCard({ release, jobId, onGrabbed }: { release: Release; jobId: string; onGrabbed: () => void }) {
  const grabMutation = useGrabRelease();

  const handleGrab = () => {
    grabMutation.mutate(
      { jobId, guid: release.guid, indexerId: release.indexerId },
      {
        onSuccess: () => {
          toast('Release grabbed — downloading', 'success');
          onGrabbed();
        },
        onError: () => toast('Failed to grab release', 'error'),
      }
    );
  };

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg ${release.rejected ? 'opacity-40' : 'hover:bg-bg-secondary/50'} transition-colors`}>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-mono truncate">{release.title}</p>
        <div className="flex items-center gap-2 mt-1 text-xs text-text-tertiary">
          <span>{release.quality}</span>
          <span>·</span>
          <span>{release.sizeDisplay}</span>
          {release.seeders != null && (
            <>
              <span>·</span>
              <span>{release.seeders} seeders</span>
            </>
          )}
          <span>·</span>
          <span>{release.indexer}</span>
          {release.score > 0 && (
            <>
              <span>·</span>
              <span className="text-accent">+{release.score}</span>
            </>
          )}
        </div>
      </div>
      <ProtocolBadge protocol={release.protocol} />
      {!release.rejected ? (
        <Button
          size="sm"
          onClick={handleGrab}
          loading={grabMutation.isPending}
          className="shrink-0"
        >
          <Download className="h-3.5 w-3.5" />
        </Button>
      ) : (
        <span className="text-xs text-red-400 shrink-0">Rejected</span>
      )}
    </div>
  );
}

export function ChooseReleaseModal({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const { data: releases, isLoading, error } = useReleases(jobId, true);
  const [showAll, setShowAll] = useState(false);

  const recommended = releases?.filter((r) => r.recommended && !r.rejected) ?? [];
  const rest = releases?.filter((r) => !r.recommended) ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" onClick={onClose}>
      <div
        className="bg-bg-primary rounded-xl border border-white/10 w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h3 className="text-lg font-bold">Choose Release</h3>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto flex-1 p-4 space-y-4">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Spinner />
              <span className="ml-2 text-sm text-text-secondary">Searching releases...</span>
            </div>
          )}

          {error && (
            <p className="text-sm text-red-400 text-center py-8">Failed to fetch releases. Try again.</p>
          )}

          {releases && releases.length === 0 && (
            <p className="text-sm text-text-secondary text-center py-8">No releases found.</p>
          )}

          {/* Recommended */}
          {recommended.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                Recommended
              </h4>
              <div className="space-y-1">
                {recommended.map((r) => (
                  <ReleaseCard key={r.guid} release={r} jobId={jobId} onGrabbed={onClose} />
                ))}
              </div>
            </div>
          )}

          {/* Show all toggle */}
          {rest.length > 0 && (
            <div>
              <button
                onClick={() => setShowAll(!showAll)}
                className="flex items-center gap-1 text-xs text-text-secondary hover:text-text-primary transition-colors"
              >
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAll ? 'rotate-180' : ''}`} />
                {showAll ? 'Hide' : 'Show'} all releases ({rest.length})
              </button>
              {showAll && (
                <div className="space-y-1 mt-2">
                  {rest.map((r) => (
                    <ReleaseCard key={r.guid} release={r} jobId={jobId} onGrabbed={onClose} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

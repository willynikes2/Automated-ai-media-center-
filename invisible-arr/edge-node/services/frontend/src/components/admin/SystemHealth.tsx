import { Card } from '@/components/ui/Card';
import { RDStatus } from '@/components/admin/RDStatus';
import { useSystemHealth, useJellyfinInfo, useLibraryCounts } from '@/hooks/useAdmin';
import { CheckCircle, XCircle, Server, Database, Film, Tv, Activity } from 'lucide-react';

function StatusRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle className="h-4 w-4 text-status-available shrink-0" />
        ) : (
          <XCircle className="h-4 w-4 text-status-failed shrink-0" />
        )}
        <span className={ok ? 'text-text-primary' : 'text-status-failed'}>{label}</span>
      </div>
      {detail && <span className="text-xs text-text-tertiary">{detail}</span>}
    </div>
  );
}

export function SystemHealth() {
  const { data: health, isLoading: healthLoading } = useSystemHealth();
  const { data: jfInfo, isLoading: jfLoading } = useJellyfinInfo();
  const { data: counts } = useLibraryCounts();

  return (
    <div className="space-y-6">
      {/* API Health */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="h-5 w-5 text-accent" />
          <h3 className="font-semibold">API Health</h3>
        </div>
        {healthLoading ? (
          <p className="text-sm text-text-secondary">Checking...</p>
        ) : (
          <div className="divide-y divide-white/5">
            <StatusRow label="Agent API" ok={health?.status === 'ok'} detail={health?.version} />
            <StatusRow label="Database" ok={health?.db === 'ok'} />
            <StatusRow label="Redis" ok={health?.redis === 'ok'} />
          </div>
        )}
      </Card>

      {/* Jellyfin Server */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Server className="h-5 w-5 text-accent" />
          <h3 className="font-semibold">Jellyfin Server</h3>
        </div>
        {jfLoading ? (
          <p className="text-sm text-text-secondary">Checking...</p>
        ) : !jfInfo ? (
          <div className="flex items-center gap-2 text-sm text-status-failed">
            <XCircle className="h-4 w-4" />
            <span>Jellyfin unreachable</span>
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-secondary">Version</span>
              <span>{jfInfo.Version}</span>
            </div>
            {jfInfo.OperatingSystem && (
              <div className="flex justify-between">
                <span className="text-text-secondary">OS</span>
                <span>{jfInfo.OperatingSystem}</span>
              </div>
            )}
            {jfInfo.ServerName && (
              <div className="flex justify-between">
                <span className="text-text-secondary">Server Name</span>
                <span>{jfInfo.ServerName}</span>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Library Counts */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Database className="h-5 w-5 text-accent" />
          <h3 className="font-semibold">Library</h3>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary/50">
            <Film className="h-5 w-5 text-text-secondary" />
            <div>
              <p className="text-xl font-bold">{counts?.movies ?? 0}</p>
              <p className="text-xs text-text-secondary">Movies</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary/50">
            <Tv className="h-5 w-5 text-text-secondary" />
            <div>
              <p className="text-xl font-bold">{counts?.shows ?? 0}</p>
              <p className="text-xs text-text-secondary">TV Shows</p>
            </div>
          </div>
        </div>
      </Card>

      {/* Real-Debrid Status */}
      <RDStatus />
    </div>
  );
}

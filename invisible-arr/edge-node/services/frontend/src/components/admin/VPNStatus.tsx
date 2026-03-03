import { Card } from '@/components/ui/Card';
import { useVPNStatus } from '@/hooks/useAdmin';
import { Shield, CheckCircle, XCircle } from 'lucide-react';

export function VPNStatus() {
  const { data, isLoading, isError } = useVPNStatus();

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Shield className="h-5 w-5 text-accent" />
        <h3 className="font-semibold">VPN (Gluetun)</h3>
      </div>

      {isLoading ? (
        <p className="text-sm text-text-secondary">Checking...</p>
      ) : isError || !data?.enabled ? (
        <p className="text-sm text-text-secondary">
          VPN is not enabled. Enable with <code className="bg-bg-tertiary px-1 rounded">--profile vpn</code>.
        </p>
      ) : (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between items-center">
            <span className="text-text-secondary">Status</span>
            <span className="flex items-center gap-1.5">
              {data.connected ? (
                <>
                  <CheckCircle className="h-4 w-4 text-status-available" />
                  <span className="text-status-available">Connected</span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-status-failed" />
                  <span className="text-status-failed">Disconnected</span>
                </>
              )}
            </span>
          </div>
          {data.provider && (
            <div className="flex justify-between">
              <span className="text-text-secondary">Provider</span>
              <span>{data.provider}</span>
            </div>
          )}
          {data.public_ip && (
            <div className="flex justify-between">
              <span className="text-text-secondary">Public IP</span>
              <span className="font-mono text-xs">{data.public_ip}</span>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

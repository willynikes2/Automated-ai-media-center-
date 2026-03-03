import { Card } from '@/components/ui/Card';
import { Shield } from 'lucide-react';

export function VPNStatus() {
  // VPN status would come from gluetun's health endpoint if accessible
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Shield className="h-5 w-5 text-accent" />
        <h3 className="font-semibold">VPN (Gluetun)</h3>
      </div>
      <p className="text-sm text-text-secondary">
        VPN status is available when the VPN profile is active.
        Enable with <code className="bg-bg-tertiary px-1 rounded">--profile vpn</code>.
      </p>
    </Card>
  );
}

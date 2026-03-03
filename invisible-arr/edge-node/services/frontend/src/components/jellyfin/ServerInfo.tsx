import { Card } from '@/components/ui/Card';
import { useJellyfinInfo } from '@/hooks/useAdmin';
import { Server } from 'lucide-react';

export function ServerInfo() {
  const { data } = useJellyfinInfo();
  if (!data) return null;

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Server className="h-5 w-5 text-accent" />
        <h3 className="font-semibold">Jellyfin Server</h3>
      </div>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between"><span className="text-text-secondary">Version</span><span>{data.Version}</span></div>
        <div className="flex justify-between"><span className="text-text-secondary">OS</span><span>{data.OperatingSystem}</span></div>
        <div className="flex justify-between"><span className="text-text-secondary">Architecture</span><span>{data.SystemArchitecture}</span></div>
      </div>
    </Card>
  );
}

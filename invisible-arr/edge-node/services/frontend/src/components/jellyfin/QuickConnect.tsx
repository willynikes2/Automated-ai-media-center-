import { useState, useEffect } from 'react';
import { initiateQuickConnect, checkQuickConnect } from '@/api/jellyfin';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { toast } from '@/components/ui/Toast';
import { RefreshCw, CheckCircle } from 'lucide-react';

export function QuickConnect() {
  const [code, setCode] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    setAuthenticated(false);
    try {
      const data = await initiateQuickConnect();
      setCode(data.Code);
      setSecret(data.Secret);
    } catch {
      toast('Failed to generate Quick Connect code', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Poll for auth
  useEffect(() => {
    if (!secret || authenticated) return;
    const interval = setInterval(async () => {
      try {
        const res = await checkQuickConnect(secret);
        if (res.Authenticated) {
          setAuthenticated(true);
          toast('Device authenticated!', 'success');
          clearInterval(interval);
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [secret, authenticated]);

  return (
    <Card className="p-6 text-center">
      <h3 className="font-semibold text-lg mb-2">Quick Connect</h3>
      <p className="text-sm text-text-secondary mb-6 max-w-sm mx-auto">
        Generate a code to link media apps on your TV, phone, or other devices.
      </p>

      {authenticated ? (
        <div className="flex flex-col items-center gap-3">
          <CheckCircle className="h-12 w-12 text-status-available" />
          <p className="text-lg font-semibold text-status-available">Authenticated!</p>
          <Button variant="secondary" onClick={generate}>
            <RefreshCw className="h-4 w-4" /> Generate New Code
          </Button>
        </div>
      ) : code ? (
        <div className="space-y-4">
          <div className="text-5xl font-mono font-bold tracking-[0.3em] text-accent">{code}</div>
          <p className="text-sm text-text-secondary">Enter this code in your media app to connect.</p>
          <p className="text-xs text-text-tertiary animate-pulse">Waiting for device...</p>
          <Button variant="secondary" onClick={generate} size="sm">
            <RefreshCw className="h-4 w-4" /> New Code
          </Button>
        </div>
      ) : (
        <Button onClick={generate} loading={loading} size="lg">
          Generate Code
        </Button>
      )}

      <div className="mt-6 text-left">
        <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">How to use</h4>
        <ol className="text-sm text-text-secondary space-y-1 list-decimal list-inside">
          <li>Click "Generate Code" above</li>
          <li>Open your media app (Jellyfin) on any device</li>
          <li>Go to Settings → Quick Connect</li>
          <li>Enter the code shown above</li>
          <li>The device will be linked automatically</li>
        </ol>
      </div>
    </Card>
  );
}

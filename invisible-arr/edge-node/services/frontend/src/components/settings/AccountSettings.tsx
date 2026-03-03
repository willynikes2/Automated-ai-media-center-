import { useState } from 'react';
import { Copy, Check, Eye, EyeOff } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useAuthStore } from '@/stores/authStore';

export function AccountSettings() {
  const user = useAuthStore((s) => s.user);
  const apiKey = useAuthStore((s) => s.apiKey);
  const [showKey, setShowKey] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyKey = () => {
    if (apiKey) navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className="p-5 space-y-4">
      <h3 className="font-semibold">Account</h3>

      <div>
        <label className="text-xs text-text-tertiary uppercase tracking-wider">Display Name</label>
        <p className="text-sm mt-1">{user?.name ?? 'Unknown'}</p>
      </div>

      <div>
        <label className="text-xs text-text-tertiary uppercase tracking-wider">API Key</label>
        <div className="flex items-center gap-2 mt-1">
          <code className="text-xs bg-bg-tertiary rounded px-2 py-1.5 flex-1 font-mono">
            {showKey ? apiKey : '••••••••••••••••••••••••'}
          </code>
          <button onClick={() => setShowKey(!showKey)} className="p-2 rounded-lg hover:bg-bg-tertiary text-text-secondary">
            {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
          <button onClick={copyKey} className="p-2 rounded-lg hover:bg-bg-tertiary text-text-secondary">
            {copied ? <Check className="h-4 w-4 text-status-available" /> : <Copy className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <div>
        <label className="text-xs text-text-tertiary uppercase tracking-wider">Role</label>
        <p className="text-sm mt-1 capitalize">{user?.role ?? 'user'}</p>
      </div>
    </Card>
  );
}

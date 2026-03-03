import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { useInvites, useCreateInvite } from '@/hooks/useAdmin';
import { Copy, Check, Plus, Link } from 'lucide-react';
import type { InviteData } from '@/api/admin';

const TIER_COLORS: Record<string, string> = {
  starter: 'bg-gray-500/20 text-gray-400',
  pro: 'bg-indigo-500/20 text-indigo-400',
  family: 'bg-emerald-500/20 text-emerald-400',
  power: 'bg-violet-500/20 text-violet-400',
};

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 text-xs text-text-secondary hover:text-accent transition-colors"
      title={label ?? 'Copy'}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-status-available" /> : <Copy className="h-3.5 w-3.5" />}
      {label && <span>{copied ? 'Copied!' : label}</span>}
    </button>
  );
}

function InviteRow({ invite }: { invite: InviteData }) {
  const isExpired = !invite.is_active || (invite.expires_at && new Date(invite.expires_at) < new Date());
  const usagePct = invite.max_uses > 0 ? Math.min((invite.times_used / invite.max_uses) * 100, 100) : 0;
  const registrationUrl = `${window.location.origin}/register?invite=${invite.code}`;

  return (
    <div className={`p-4 rounded-lg bg-bg-tertiary/30 ${isExpired ? 'opacity-50' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0 space-y-2">
          {/* Code + tier */}
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-sm font-mono bg-bg-tertiary px-2 py-0.5 rounded">{invite.code}</code>
            <Badge className={TIER_COLORS[invite.tier] ?? TIER_COLORS.starter}>{invite.tier}</Badge>
            {isExpired && (
              <Badge className="bg-status-failed/20 text-status-failed">Expired</Badge>
            )}
          </div>

          {/* Usage bar */}
          <div className="flex items-center gap-2">
            <div className="w-24 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-accent transition-all"
                style={{ width: `${usagePct}%` }}
              />
            </div>
            <span className="text-xs text-text-tertiary">
              {invite.times_used}/{invite.max_uses} uses
            </span>
          </div>

          {/* Expiry */}
          {invite.expires_at && (
            <p className="text-xs text-text-tertiary">
              Expires: {new Date(invite.expires_at).toLocaleDateString()}
            </p>
          )}
        </div>

        {/* Copy buttons */}
        <div className="flex flex-col gap-1.5 shrink-0">
          <CopyButton text={invite.code} label="Code" />
          <CopyButton text={registrationUrl} label="Link" />
        </div>
      </div>
    </div>
  );
}

export function InviteManager() {
  const { data: invites, isLoading } = useInvites();
  const createInvite = useCreateInvite();

  const [tier, setTier] = useState('starter');
  const [maxUses, setMaxUses] = useState(1);
  const [expiresInDays, setExpiresInDays] = useState<number | ''>('');

  const handleCreate = () => {
    createInvite.mutate(
      {
        tier,
        max_uses: maxUses,
        ...(expiresInDays ? { expires_in_days: Number(expiresInDays) } : {}),
      },
      {
        onSuccess: () => {
          setMaxUses(1);
          setExpiresInDays('');
        },
      }
    );
  };

  return (
    <div className="space-y-6">
      {/* Create invite form */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Plus className="h-5 w-5 text-accent" />
          <h3 className="font-semibold">Create Invite</h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 items-end">
          <Select
            label="Tier"
            value={tier}
            onChange={(e) => setTier(e.target.value)}
            options={[
              { value: 'starter', label: 'Starter' },
              { value: 'pro', label: 'Pro' },
              { value: 'family', label: 'Family' },
              { value: 'power', label: 'Power' },
            ]}
          />
          <Input
            label="Max Uses"
            type="number"
            min={1}
            value={maxUses}
            onChange={(e) => setMaxUses(Number(e.target.value))}
          />
          <Input
            label="Expires (days)"
            type="number"
            min={1}
            placeholder="Never"
            value={expiresInDays}
            onChange={(e) => setExpiresInDays(e.target.value ? Number(e.target.value) : '')}
          />
          <Button loading={createInvite.isPending} onClick={handleCreate}>
            Create
          </Button>
        </div>
      </Card>

      {/* Invite list */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Link className="h-5 w-5 text-accent" />
          <h3 className="font-semibold">Invites</h3>
          {invites && (
            <span className="text-xs text-text-tertiary">({invites.length})</span>
          )}
        </div>
        {isLoading ? (
          <p className="text-sm text-text-secondary">Loading invites...</p>
        ) : !invites?.length ? (
          <p className="text-sm text-text-secondary">No invites created yet.</p>
        ) : (
          <div className="space-y-2">
            {invites.map((invite) => (
              <InviteRow key={invite.id} invite={invite} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

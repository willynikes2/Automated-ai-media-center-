import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { useResellerStats, useResellerInvites, useCreateResellerInvite } from '@/hooks/useReseller';
import { Users, UserCheck, Ticket, HardDrive, Plus, Link, Copy, Check } from 'lucide-react';
import type { InviteData } from '@/api/admin';

// ── Tier colors ─────────────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  starter: 'bg-gray-500/20 text-gray-400',
  pro: 'bg-indigo-500/20 text-indigo-400',
  family: 'bg-emerald-500/20 text-emerald-400',
  power: 'bg-violet-500/20 text-violet-400',
};

// ── Stat card ───────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-lg bg-accent/10">
          <Icon className="h-5 w-5 text-accent" />
        </div>
        <div>
          <p className="text-2xl font-bold text-text-primary">{value}</p>
          <p className="text-sm text-text-secondary">{label}</p>
        </div>
      </div>
    </Card>
  );
}

// ── Copy button ─────────────────────────────────────────────

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

// ── Invite row ──────────────────────────────────────────────

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

// ── Main page ───────────────────────────────────────────────

export function ResellerPage() {
  const { data: stats, isLoading: statsLoading } = useResellerStats();
  const { data: invites, isLoading: invitesLoading } = useResellerInvites();
  const createInvite = useCreateResellerInvite();

  const [maxUses, setMaxUses] = useState(1);
  const [expiresInDays, setExpiresInDays] = useState<number | ''>('');

  const handleCreate = () => {
    createInvite.mutate(
      {
        max_uses: maxUses,
        ...(expiresInDays ? { expires_in_days: Number(expiresInDays) } : {}),
      },
      {
        onSuccess: () => {
          setMaxUses(1);
          setExpiresInDays('');
        },
      },
    );
  };

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">Reseller Dashboard</h1>
      <p className="text-sm text-text-secondary mb-6">
        Manage your invites and track referred users.
      </p>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Referred Users"
          value={statsLoading ? '--' : (stats?.total_referred ?? 0)}
          icon={Users}
        />
        <StatCard
          label="Active Users"
          value={statsLoading ? '--' : (stats?.active_referred ?? 0)}
          icon={UserCheck}
        />
        <StatCard
          label="Invites Created"
          value={statsLoading ? '--' : (stats?.total_invites ?? 0)}
          icon={Ticket}
        />
        <StatCard
          label="Storage Used"
          value={statsLoading ? '--' : `${stats?.storage_used_gb ?? 0} GB`}
          icon={HardDrive}
        />
      </div>

      {/* Create invite */}
      <Card className="p-5 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Plus className="h-5 w-5 text-accent" />
          <h3 className="font-semibold">Create Invite</h3>
          <span className="text-xs text-text-tertiary">(Starter tier, max 5 uses)</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <Input
            label="Max Uses"
            type="number"
            min={1}
            max={5}
            value={maxUses}
            onChange={(e) => setMaxUses(Math.min(Number(e.target.value), 5))}
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
            Create Invite
          </Button>
        </div>
      </Card>

      {/* Invite list */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Link className="h-5 w-5 text-accent" />
          <h3 className="font-semibold">Your Invites</h3>
          {invites && (
            <span className="text-xs text-text-tertiary">({invites.length})</span>
          )}
        </div>
        {invitesLoading ? (
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

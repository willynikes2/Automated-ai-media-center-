import { QualityPrefs } from '@/components/settings/QualityPrefs';
import { StoragePrefs } from '@/components/settings/StoragePrefs';
import { AccountSettings } from '@/components/settings/AccountSettings';
import { QuickConnect } from '@/components/jellyfin/QuickConnect';
import { Card } from '@/components/ui/Card';
import { useStorageInfo } from '@/hooks/useMedia';
import { useAuthStore } from '@/stores/authStore';
import { useSessionCheck } from '@/hooks/useAuth';
import { HardDrive, User, Crown } from 'lucide-react';
import type { UserRole, UserTier } from '@/stores/authStore';

/* ── Badge helpers ─────────────────────────────────────────────── */

const TIER_COLORS: Record<UserTier, string> = {
  starter: 'bg-gray-500/20 text-gray-400',
  pro: 'bg-indigo-500/20 text-indigo-400',
  family: 'bg-emerald-500/20 text-emerald-400',
  power: 'bg-violet-500/20 text-violet-400',
};

const ROLE_COLORS: Record<UserRole, string> = {
  admin: 'bg-red-500/20 text-red-400',
  reseller: 'bg-amber-500/20 text-amber-400',
  user: 'bg-gray-500/20 text-gray-400',
};

function RoleBadge({ role }: { role: UserRole }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${ROLE_COLORS[role] ?? ROLE_COLORS.user}`}>
      {role}
    </span>
  );
}

function TierBadge({ tier }: { tier: UserTier }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${TIER_COLORS[tier] ?? TIER_COLORS.starter}`}>
      {tier}
    </span>
  );
}

/* ── Account Profile ───────────────────────────────────────────── */

function AccountProfile() {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;

  return (
    <Card className="p-5">
      <div className="flex items-center gap-4">
        <div className="h-14 w-14 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
          <span className="text-xl font-bold text-accent">
            {user.name?.[0]?.toUpperCase() ?? '?'}
          </span>
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold truncate">{user.name}</h2>
          {user.email && (
            <p className="text-sm text-text-secondary truncate">{user.email}</p>
          )}
          <div className="flex items-center gap-2 mt-1">
            <RoleBadge role={user.role} />
            <TierBadge tier={user.tier} />
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ── Tier Info ──────────────────────────────────────────────────── */

function TierInfo() {
  const user = useAuthStore((s) => s.user);
  const { data: profile } = useSessionCheck();

  if (!user || !profile) return null;

  const tier = user.tier;
  const isUpgradable = tier === 'starter' || tier === 'pro';

  const limits = [
    {
      label: 'Storage Quota',
      value: profile.storage_quota_gb != null ? `${profile.storage_quota_gb} GB` : 'Unlimited',
      used: profile.storage_used_gb != null ? `${profile.storage_used_gb.toFixed(1)} GB used` : null,
    },
    {
      label: 'Max Resolution',
      value: profile.max_resolution ? `${profile.max_resolution}p` : '4K',
    },
    {
      label: 'Concurrent Jobs',
      value: profile.max_concurrent_jobs != null ? String(profile.max_concurrent_jobs) : 'Unlimited',
    },
    {
      label: 'Daily Requests',
      value: profile.max_requests_per_day != null ? String(profile.max_requests_per_day) : 'Unlimited',
    },
  ];

  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Crown className="h-5 w-5" /> Plan &amp; Limits
      </h2>
      <div className="grid grid-cols-2 gap-4">
        {limits.map((item) => (
          <div key={item.label} className="p-3 rounded-lg bg-bg-tertiary">
            <p className="text-xs text-text-tertiary">{item.label}</p>
            <p className="text-sm font-semibold mt-0.5">{item.value}</p>
            {'used' in item && item.used && (
              <p className="text-[10px] text-text-tertiary mt-0.5">{item.used}</p>
            )}
          </div>
        ))}
      </div>
      {isUpgradable && (
        <p className="text-xs text-accent mt-3">
          Upgrade your plan to unlock higher limits and more features.
        </p>
      )}
    </Card>
  );
}

/* ── Storage Display ───────────────────────────────────────────── */

function StorageDisplay() {
  const { data, isLoading } = useStorageInfo();

  if (isLoading || !data) return null;

  const pct = data.total_gb > 0 ? (data.used_gb / data.total_gb) * 100 : 0;
  const color = pct > 90 ? 'bg-status-failed' : pct > 70 ? 'bg-yellow-500' : 'bg-status-available';

  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <HardDrive className="h-5 w-5" /> Storage
      </h2>

      <div className="space-y-3">
        <div className="h-3 bg-bg-tertiary rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(100, pct)}%` }} />
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-text-tertiary text-xs">Used</p>
            <p className="font-medium">{data.used_gb.toFixed(1)} GB</p>
          </div>
          <div>
            <p className="text-text-tertiary text-xs">Free</p>
            <p className="font-medium">{data.free_gb.toFixed(1)} GB</p>
          </div>
          <div>
            <p className="text-text-tertiary text-xs">Media</p>
            <p className="font-medium">{data.media_gb.toFixed(1)} GB</p>
          </div>
          <div>
            <p className="text-text-tertiary text-xs">Total</p>
            <p className="font-medium">{data.total_gb.toFixed(1)} GB</p>
          </div>
        </div>

        <p className="text-xs text-text-tertiary">{data.prune_policy}</p>
      </div>
    </Card>
  );
}

/* ── Settings Page ─────────────────────────────────────────────── */

export function SettingsPage() {
  return (
    <div className="px-4 md:px-8 py-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-sm text-text-secondary">Configure your media preferences and account.</p>
      </div>

      <AccountProfile />
      <TierInfo />
      <StorageDisplay />
      <QualityPrefs />
      <StoragePrefs />
      <AccountSettings />

      <Card className="p-5">
        <h2 className="text-lg font-semibold mb-1">Device Pairing</h2>
        <p className="text-xs text-text-secondary mb-4">
          Use Quick Connect to link external devices like TVs and streaming boxes to your Jellyfin account.
        </p>
        <QuickConnect />
      </Card>
    </div>
  );
}

import { useState, useMemo } from 'react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { useAdminUsers, useUpdateUser, useDeactivateUser } from '@/hooks/useAdmin';
import { Search, ChevronDown, ChevronUp } from 'lucide-react';
import type { AdminUser, AdminUserUpdate } from '@/api/admin';

const TIER_COLORS: Record<string, string> = {
  starter: 'bg-gray-500/20 text-gray-400',
  pro: 'bg-indigo-500/20 text-indigo-400',
  family: 'bg-emerald-500/20 text-emerald-400',
  power: 'bg-violet-500/20 text-violet-400',
};

const ROLE_COLORS: Record<string, string> = {
  admin: 'bg-red-500/20 text-red-400',
  reseller: 'bg-amber-500/20 text-amber-400',
  user: 'bg-gray-500/20 text-gray-400',
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function StorageBar({ used, quota }: { used: number; quota: number }) {
  const pct = quota > 0 ? Math.min((used / quota) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${pct > 90 ? 'bg-status-failed' : 'bg-accent'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-text-tertiary">{used.toFixed(1)}/{quota}GB</span>
    </div>
  );
}

function UserEditForm({ user, onClose }: { user: AdminUser; onClose: () => void }) {
  const updateUser = useUpdateUser();
  const deactivateUser = useDeactivateUser();

  const [form, setForm] = useState<AdminUserUpdate>({
    role: user.role,
    tier: user.tier,
    is_active: user.is_active,
    storage_quota_gb: user.storage_quota_gb,
    max_concurrent_jobs: user.max_concurrent_jobs,
    max_requests_per_day: user.max_requests_per_day,
  });

  const handleSave = () => {
    updateUser.mutate({ id: user.id, body: form }, { onSuccess: onClose });
  };

  const handleDeactivate = () => {
    if (confirm(`Deactivate user "${user.name}"?`)) {
      deactivateUser.mutate(user.id, { onSuccess: onClose });
    }
  };

  return (
    <div className="p-4 border-t border-white/5 bg-bg-tertiary/30 space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Select
          label="Role"
          value={form.role ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
          options={[
            { value: 'user', label: 'User' },
            { value: 'admin', label: 'Admin' },
            { value: 'reseller', label: 'Reseller' },
          ]}
        />
        <Select
          label="Tier"
          value={form.tier ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, tier: e.target.value }))}
          options={[
            { value: 'starter', label: 'Starter' },
            { value: 'pro', label: 'Pro' },
            { value: 'family', label: 'Family' },
            { value: 'power', label: 'Power' },
          ]}
        />
        <div className="flex items-end">
          <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active ?? true}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              className="rounded bg-bg-tertiary border-white/10"
            />
            Active
          </label>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Input
          label="Storage Quota (GB)"
          type="number"
          value={form.storage_quota_gb ?? 0}
          onChange={(e) => setForm((f) => ({ ...f, storage_quota_gb: Number(e.target.value) }))}
        />
        <Input
          label="Max Concurrent Jobs"
          type="number"
          value={form.max_concurrent_jobs ?? 0}
          onChange={(e) => setForm((f) => ({ ...f, max_concurrent_jobs: Number(e.target.value) }))}
        />
        <Input
          label="Max Requests/Day"
          type="number"
          value={form.max_requests_per_day ?? 0}
          onChange={(e) => setForm((f) => ({ ...f, max_requests_per_day: Number(e.target.value) }))}
        />
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" loading={updateUser.isPending} onClick={handleSave}>
          Save
        </Button>
        <Button size="sm" variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" variant="danger" loading={deactivateUser.isPending} onClick={handleDeactivate} className="ml-auto">
          Deactivate
        </Button>
      </div>
    </div>
  );
}

export function UserManager() {
  const { data: users, isLoading } = useAdminUsers();
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!users) return [];
    if (!search.trim()) return users;
    const q = search.toLowerCase();
    return users.filter(
      (u) => u.name.toLowerCase().includes(q) || (u.email && u.email.toLowerCase().includes(q))
    );
  }, [users, search]);

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-tertiary" />
        <input
          type="text"
          placeholder="Search users..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-bg-secondary border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent/50"
        />
      </div>

      {isLoading ? (
        <p className="text-sm text-text-secondary">Loading users...</p>
      ) : !filtered.length ? (
        <p className="text-sm text-text-secondary">No users found.</p>
      ) : (
        <div className="space-y-2">
          {filtered.map((user) => {
            const isExpanded = expandedId === user.id;
            return (
              <Card key={user.id} className="overflow-hidden">
                <button
                  onClick={() => setExpandedId(isExpanded ? null : user.id)}
                  className="w-full p-4 flex items-center gap-3 text-left hover:bg-bg-tertiary/30 transition-colors"
                >
                  {/* Avatar */}
                  <div className="h-9 w-9 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
                    <span className="text-sm font-bold text-accent">
                      {user.name?.[0]?.toUpperCase() ?? '?'}
                    </span>
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm truncate">{user.name}</span>
                      {/* Active dot */}
                      <span
                        className={`h-2 w-2 rounded-full shrink-0 ${
                          user.is_active ? 'bg-status-available' : 'bg-status-failed'
                        }`}
                      />
                    </div>
                    {user.email && (
                      <p className="text-xs text-text-tertiary truncate">{user.email}</p>
                    )}
                  </div>

                  {/* Badges */}
                  <div className="hidden sm:flex items-center gap-2 shrink-0">
                    <Badge className={ROLE_COLORS[user.role] ?? ROLE_COLORS.user}>
                      {user.role}
                    </Badge>
                    <Badge className={TIER_COLORS[user.tier] ?? TIER_COLORS.starter}>
                      {user.tier}
                    </Badge>
                  </div>

                  {/* Storage */}
                  <div className="hidden md:block shrink-0">
                    <StorageBar used={user.storage_used_gb} quota={user.storage_quota_gb} />
                  </div>

                  {/* Last login */}
                  <span className="hidden lg:block text-xs text-text-tertiary whitespace-nowrap shrink-0">
                    {timeAgo(user.last_login)}
                  </span>

                  {/* Expand icon */}
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4 text-text-tertiary shrink-0" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-text-tertiary shrink-0" />
                  )}
                </button>

                {/* Mobile badges row */}
                <div className="flex sm:hidden items-center gap-2 px-4 pb-2">
                  <Badge className={ROLE_COLORS[user.role] ?? ROLE_COLORS.user}>
                    {user.role}
                  </Badge>
                  <Badge className={TIER_COLORS[user.tier] ?? TIER_COLORS.starter}>
                    {user.tier}
                  </Badge>
                  <StorageBar used={user.storage_used_gb} quota={user.storage_quota_gb} />
                </div>

                {/* Edit form */}
                {isExpanded && (
                  <UserEditForm user={user} onClose={() => setExpandedId(null)} />
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

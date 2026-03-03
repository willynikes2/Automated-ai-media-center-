import { useState } from 'react';
import { AdminDashboard } from '@/components/admin/AdminDashboard';
import { UserManager } from '@/components/admin/UserManager';
import { InviteManager } from '@/components/admin/InviteManager';
import { AllJobs } from '@/components/admin/AllJobs';
import { SystemHealth } from '@/components/admin/SystemHealth';

const tabs = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'users', label: 'Users' },
  { key: 'invites', label: 'Invites' },
  { key: 'jobs', label: 'All Jobs' },
  { key: 'system', label: 'System' },
] as const;

export function AdminPage() {
  const [tab, setTab] = useState<string>('dashboard');

  return (
    <div className="px-4 md:px-8 py-6">
      <h1 className="text-2xl font-bold mb-1">Admin</h1>
      <p className="text-sm text-text-secondary mb-6">System administration and monitoring.</p>

      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit mb-6 overflow-x-auto">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
              tab === t.key ? 'bg-accent text-white' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'dashboard' && <AdminDashboard />}
      {tab === 'users' && <UserManager />}
      {tab === 'invites' && <InviteManager />}
      {tab === 'jobs' && <AllJobs />}
      {tab === 'system' && <SystemHealth />}
    </div>
  );
}

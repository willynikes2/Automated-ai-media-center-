import { useState } from 'react';
import { AdminDashboard } from '@/components/admin/AdminDashboard';
import { UserManager } from '@/components/admin/UserManager';
import { AllJobs } from '@/components/admin/AllJobs';
import { RDStatus } from '@/components/admin/RDStatus';
import { VPNStatus } from '@/components/admin/VPNStatus';
import { ServerInfo } from '@/components/jellyfin/ServerInfo';
import { LibraryStats } from '@/components/jellyfin/LibraryStats';
import { QuickConnect } from '@/components/jellyfin/QuickConnect';

const tabs = [
  { key: 'overview', label: 'Overview' },
  { key: 'users', label: 'Users' },
  { key: 'jobs', label: 'Jobs' },
  { key: 'system', label: 'System' },
  { key: 'connect', label: 'Quick Connect' },
] as const;

export function AdminPage() {
  const [tab, setTab] = useState<string>('overview');

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

      {tab === 'overview' && <AdminDashboard />}
      {tab === 'users' && <UserManager />}
      {tab === 'jobs' && <AllJobs />}
      {tab === 'system' && (
        <div className="grid gap-4 md:grid-cols-2">
          <ServerInfo />
          <LibraryStats />
          <RDStatus />
          <VPNStatus />
        </div>
      )}
      {tab === 'connect' && (
        <div className="max-w-md mx-auto">
          <QuickConnect />
        </div>
      )}
    </div>
  );
}

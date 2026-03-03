import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { MobileNav } from './MobileNav';
import BugReportButton from '@/components/ui/BugReportButton';

export function AppShell() {
  return (
    <div className="flex min-h-screen bg-bg-primary">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 pb-[calc(5rem+var(--sab))] md:pb-0">
          <Outlet />
        </main>
      </div>
      <MobileNav />
      <BugReportButton />
    </div>
  );
}

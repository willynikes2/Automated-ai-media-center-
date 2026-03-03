import { NavLink } from 'react-router-dom';
import { Compass, Search, Library, Download, Activity, Tv, Settings, Shield, Zap, LogOut } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { useLogout } from '@/hooks/useAuth';

const nav = [
  { to: '/', icon: Compass, label: 'Discover' },
  { to: '/search', icon: Search, label: 'Search' },
  { to: '/library', icon: Library, label: 'Library' },
  { to: '/requests', icon: Download, label: 'Requests' },
  { to: '/activity', icon: Activity, label: 'Activity' },
  { to: '/iptv', icon: Tv, label: 'Live TV' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export function Sidebar() {
  const isAdmin = useAuthStore((s) => s.user?.isAdmin);
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const logout = useLogout();

  return (
    <aside
      className={`hidden md:flex flex-col bg-bg-secondary border-r border-white/5 h-screen sticky top-0 transition-all duration-200 ${
        sidebarOpen ? 'w-56' : 'w-16'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-white/5">
        <div className="h-8 w-8 rounded-lg bg-accent flex items-center justify-center shrink-0">
          <Zap className="h-5 w-5 text-white" />
        </div>
        {sidebarOpen && <span className="font-bold text-lg tracking-tight">AutoMedia</span>}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-accent/15 text-accent'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
              }`
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {sidebarOpen && <span>{item.label}</span>}
          </NavLink>
        ))}

        {isAdmin && (
          <>
            <div className="my-3 border-t border-white/5" />
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-accent/15 text-accent'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                }`
              }
            >
              <Shield className="h-5 w-5 shrink-0" />
              {sidebarOpen && <span>Admin</span>}
            </NavLink>
          </>
        )}
      </nav>

      {/* Logout */}
      <div className="p-2 border-t border-white/5">
        <button
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-text-secondary hover:text-text-primary hover:bg-bg-tertiary w-full"
        >
          <LogOut className="h-5 w-5 shrink-0" />
          {sidebarOpen && <span>Sign Out</span>}
        </button>
      </div>
    </aside>
  );
}

import { NavLink } from 'react-router-dom';
import { Compass, Search, Library, Download, Activity, Tv, Settings, Shield, DollarSign, Zap, LogOut, Users, Mail } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { useLogout } from '@/hooks/useAuth';
import type { UserTier } from '@/stores/authStore';

const TIER_COLORS: Record<UserTier, string> = {
  starter: 'bg-gray-500/20 text-gray-400',
  pro: 'bg-indigo-500/20 text-indigo-400',
  family: 'bg-emerald-500/20 text-emerald-400',
  power: 'bg-violet-500/20 text-violet-400',
};

const nav = [
  { to: '/', icon: Compass, label: 'Discover' },
  { to: '/search', icon: Search, label: 'Search' },
  { to: '/library', icon: Library, label: 'Library' },
  { to: '/requests', icon: Download, label: 'Requests' },
  { to: '/activity', icon: Activity, label: 'Activity' },
  { to: '/iptv', icon: Tv, label: 'Live TV' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
    isActive
      ? 'bg-accent/15 text-accent'
      : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
  }`;

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';
  const isReseller = user?.role === 'reseller';
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
      <nav className="flex-1 py-4 space-y-1 px-2 overflow-y-auto">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={navLinkClass}
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {sidebarOpen && <span>{item.label}</span>}
          </NavLink>
        ))}

        {/* Admin section */}
        {isAdmin && (
          <>
            <div className="my-3 border-t border-white/5" />
            <NavLink to="/admin" className={navLinkClass}>
              <Shield className="h-5 w-5 shrink-0" />
              {sidebarOpen && <span>Admin</span>}
            </NavLink>
            {sidebarOpen && (
              <div className="ml-8 space-y-0.5">
                <NavLink
                  to="/admin?tab=users"
                  className="block px-3 py-1.5 rounded-md text-xs text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Users className="h-3.5 w-3.5" /> Users
                  </span>
                </NavLink>
                <NavLink
                  to="/admin?tab=invites"
                  className="block px-3 py-1.5 rounded-md text-xs text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Mail className="h-3.5 w-3.5" /> Invites
                  </span>
                </NavLink>
              </div>
            )}
          </>
        )}

        {/* Reseller section */}
        {isReseller && (
          <>
            <div className="my-3 border-t border-white/5" />
            <NavLink to="/reseller" className={navLinkClass}>
              <DollarSign className="h-5 w-5 shrink-0" />
              {sidebarOpen && <span>Reseller</span>}
            </NavLink>
          </>
        )}
      </nav>

      {/* Tier badge + Logout */}
      <div className="p-2 border-t border-white/5 space-y-1">
        {user?.tier && sidebarOpen && (
          <div className="flex items-center justify-center px-3 py-1.5">
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium capitalize ${TIER_COLORS[user.tier] ?? TIER_COLORS.starter}`}>
              {user.tier} plan
            </span>
          </div>
        )}
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

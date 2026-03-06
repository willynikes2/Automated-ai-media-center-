import { useNavigate, Link } from 'react-router-dom';
import { Search, Menu, Bell, Settings, LogOut, ChevronDown } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { useState, useRef, useEffect } from 'react';
import { useLogout } from '@/hooks/useAuth';
import type { UserTier } from '@/stores/authStore';

const TIER_COLORS: Record<UserTier, string> = {
  starter: 'bg-gray-500/20 text-gray-400',
  pro: 'bg-indigo-500/20 text-indigo-400',
  family: 'bg-emerald-500/20 text-emerald-400',
  power: 'bg-violet-500/20 text-violet-400',
};

export function TopBar() {
  const user = useAuthStore((s) => s.user);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const [query, setQuery] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const logout = useLogout();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  // Close on Escape
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [menuOpen]);

  return (
    <header className="border-b border-white/5 bg-bg-secondary/80 backdrop-blur-md sticky top-0 z-30 flex items-center gap-4 px-4 md:px-6 h-[calc(4rem+var(--sat))] pt-[var(--sat)]">
      <button onClick={toggleSidebar} className="hidden md:block text-text-secondary hover:text-text-primary">
        <Menu className="h-5 w-5" />
      </button>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex-1 max-w-xl">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-tertiary" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search movies & TV shows..."
            className="w-full bg-bg-tertiary border border-white/5 rounded-full pl-10 pr-4 py-2 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-transparent"
          />
        </div>
      </form>

      <div className="flex items-center gap-3">
        <button className="relative p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary">
          <Bell className="h-5 w-5" />
        </button>

        {/* User menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex items-center gap-2 p-1 rounded-lg hover:bg-bg-tertiary transition-colors"
          >
            {user?.tier && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium capitalize hidden sm:inline-block ${TIER_COLORS[user.tier] ?? TIER_COLORS.starter}`}>
                {user.tier}
              </span>
            )}
            <div className="h-8 w-8 rounded-full bg-accent/20 flex items-center justify-center">
              <span className="text-xs font-bold text-accent">
                {user?.name?.[0]?.toUpperCase() ?? '?'}
              </span>
            </div>
            <ChevronDown className={`h-3.5 w-3.5 text-text-tertiary transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-2 w-56 bg-bg-secondary border border-white/10 rounded-xl shadow-2xl py-1 z-50">
              {/* User info */}
              <div className="px-4 py-3 border-b border-white/5">
                <p className="text-sm font-medium text-text-primary truncate">{user?.name}</p>
                {user?.email && (
                  <p className="text-xs text-text-tertiary truncate mt-0.5">{user.email}</p>
                )}
                {user?.tier && (
                  <span className={`inline-block mt-1.5 text-[10px] px-1.5 py-0.5 rounded-full font-medium capitalize ${TIER_COLORS[user.tier] ?? TIER_COLORS.starter}`}>
                    {user.tier}
                  </span>
                )}
              </div>

              {/* Menu items */}
              <div className="py-1">
                <Link
                  to="/settings"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-3 px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
                >
                  <Settings className="h-4 w-4" />
                  Settings
                </Link>
              </div>

              <div className="border-t border-white/5 py-1">
                <button
                  onClick={() => { setMenuOpen(false); logout(); }}
                  className="flex items-center gap-3 px-4 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-bg-tertiary transition-colors w-full"
                >
                  <LogOut className="h-4 w-4" />
                  Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

import { useNavigate } from 'react-router-dom';
import { Search, Menu, Bell } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { useState } from 'react';
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
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

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

        {/* Tier badge + Avatar */}
        <div className="flex items-center gap-2">
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
        </div>
      </div>
    </header>
  );
}

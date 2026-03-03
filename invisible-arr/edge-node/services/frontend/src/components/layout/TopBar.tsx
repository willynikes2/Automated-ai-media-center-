import { useNavigate } from 'react-router-dom';
import { Search, Menu, Bell } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { useState } from 'react';

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
    <header className="h-16 border-b border-white/5 bg-bg-secondary/80 backdrop-blur-md sticky top-0 z-30 flex items-center gap-4 px-4 md:px-6">
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

        {/* Avatar */}
        <div className="h-8 w-8 rounded-full bg-accent/20 flex items-center justify-center">
          <span className="text-xs font-bold text-accent">
            {user?.name?.[0]?.toUpperCase() ?? '?'}
          </span>
        </div>
      </div>
    </header>
  );
}

import { useState, useEffect } from 'react';
import { Search, X } from 'lucide-react';

interface Props {
  initialQuery?: string;
  onSearch: (query: string) => void;
  placeholder?: string;
}

export function SearchBar({ initialQuery = '', onSearch, placeholder = 'Search movies & TV shows...' }: Props) {
  const [value, setValue] = useState(initialQuery);

  useEffect(() => {
    const timer = setTimeout(() => {
      onSearch(value);
    }, 400);
    return () => clearTimeout(timer);
  }, [value, onSearch]);

  return (
    <div className="relative">
      <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-text-tertiary" />
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-bg-secondary border border-white/10 rounded-xl pl-12 pr-10 py-3 text-base text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent/50"
      />
      {value && (
        <button
          onClick={() => setValue('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-bg-tertiary text-text-tertiary"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

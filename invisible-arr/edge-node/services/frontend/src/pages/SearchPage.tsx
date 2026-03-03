import { useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SearchBar } from '@/components/media/SearchBar';
import { MediaGrid } from '@/components/media/MediaGrid';
import { EmptyState } from '@/components/ui/EmptyState';
import { FullSpinner } from '@/components/ui/Spinner';
import { useTMDBSearch } from '@/hooks/useMedia';
import { Search as SearchIcon } from 'lucide-react';

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const initialQuery = params.get('q') ?? '';
  const [query, setQuery] = useState(initialQuery);
  const { data, isLoading } = useTMDBSearch(query);

  const handleSearch = useCallback((q: string) => {
    setQuery(q);
    if (q) setParams({ q });
    else setParams({});
  }, [setParams]);

  return (
    <div className="px-4 md:px-8 py-6">
      <div className="max-w-2xl mx-auto mb-8">
        <SearchBar initialQuery={initialQuery} onSearch={handleSearch} />
      </div>

      {isLoading ? (
        <FullSpinner />
      ) : !query ? (
        <EmptyState
          icon={SearchIcon}
          title="Search for movies & TV shows"
          description="Find something to watch and request it."
        />
      ) : !data?.results?.length ? (
        <EmptyState
          icon={SearchIcon}
          title="No results found"
          description={`Nothing matched "${query}". Try a different search.`}
        />
      ) : (
        <>
          <p className="text-sm text-text-secondary mb-4">{data.total_results} results for "{query}"</p>
          <MediaGrid items={data.results} />
        </>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Search as SearchIcon, Star } from "lucide-react";
import { searchTMDB, type TMDBResult } from "@/lib/api";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TMDBResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const data = await searchTMDB(query.trim());
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold text-white mb-6">Search</h2>

      <form onSubmit={handleSearch} className="mb-8">
        <div className="relative">
          <SearchIcon
            size={20}
            className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search movies & TV shows..."
            className="w-full bg-surface-800 border border-surface-600 rounded-xl pl-12 pr-4 py-3.5 text-white placeholder-gray-500 focus:outline-none focus:border-brand-500 transition-colors"
          />
        </div>
      </form>

      {loading && (
        <div className="text-center py-12 text-gray-500">Searching...</div>
      )}

      {!loading && searched && results.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          No results found for &quot;{query}&quot;
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {results.map((item) => (
          <MediaCard key={`${item.media_type}-${item.id}`} item={item} />
        ))}
      </div>
    </div>
  );
}

function MediaCard({ item }: { item: TMDBResult }) {
  const title = item.title || item.name || "Unknown";
  const year = (item.release_date || item.first_air_date || "").slice(0, 4);
  const poster = item.poster_path
    ? `https://image.tmdb.org/t/p/w342${item.poster_path}`
    : null;

  return (
    <Link
      href={`/request/${item.media_type}/${item.id}`}
      className="group bg-surface-800 rounded-xl border border-surface-600 overflow-hidden hover:border-brand-500 transition-all hover:scale-[1.02]"
    >
      <div className="aspect-[2/3] relative bg-surface-700">
        {poster ? (
          <Image
            src={poster}
            alt={title}
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 20vw"
            className="object-cover"
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-600 text-sm">
            No Poster
          </div>
        )}
        <div className="absolute top-2 right-2 bg-black/70 rounded-md px-1.5 py-0.5 text-xs font-medium uppercase">
          {item.media_type}
        </div>
      </div>
      <div className="p-3">
        <p className="text-sm font-medium text-white truncate group-hover:text-brand-500 transition-colors">
          {title}
        </p>
        <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
          {year && <span>{year}</span>}
          {item.vote_average > 0 && (
            <span className="flex items-center gap-0.5">
              <Star size={10} className="text-yellow-500" />
              {item.vote_average.toFixed(1)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

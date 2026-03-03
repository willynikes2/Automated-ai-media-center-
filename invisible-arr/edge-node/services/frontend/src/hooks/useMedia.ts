import { useQuery } from '@tanstack/react-query';
import { searchTMDB, getTrending, getPopular, getTMDBDetail, getLatestMedia, getLibraryItems } from '@/api/media';

export function useTMDBSearch(query: string, page = 1) {
  return useQuery({
    queryKey: ['tmdb-search', query, page],
    queryFn: () => searchTMDB(query, page),
    enabled: query.length >= 2,
    staleTime: 30_000,
  });
}

export function useTrending(type: 'movie' | 'tv' = 'movie') {
  return useQuery({
    queryKey: ['trending', type],
    queryFn: () => getTrending(type),
    staleTime: 5 * 60_000,
  });
}

export function usePopular(type: 'movie' | 'tv' = 'movie') {
  return useQuery({
    queryKey: ['popular', type],
    queryFn: () => getPopular(type),
    staleTime: 5 * 60_000,
  });
}

export function useTMDBDetail(type: 'movie' | 'tv', id: number) {
  return useQuery({
    queryKey: ['tmdb-detail', type, id],
    queryFn: () => getTMDBDetail(type, id),
    enabled: !!id,
    staleTime: 10 * 60_000,
  });
}

export function useLatestMedia() {
  return useQuery({
    queryKey: ['jellyfin-latest'],
    queryFn: getLatestMedia,
    staleTime: 60_000,
  });
}

export function useLibrary(type: 'Movie' | 'Series', params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['library', type, params],
    queryFn: () => getLibraryItems(type, params),
    staleTime: 60_000,
  });
}

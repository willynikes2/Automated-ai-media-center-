import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { searchTMDB, getTrending, getPopular, getTMDBDetail, getLatestMedia, getLibraryItems, getJellyfinItem, deleteJellyfinItem, getStorageInfo, getTVSeasons, getTVSeasonDetail, deleteLibraryItem, getJellyfinLibrary, getQuotaInfo } from '@/api/media';
import type { DeleteMediaRequest } from '@/api/media';
import { useAuthStore } from '@/stores/authStore';

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

export function useLibrary(mediaType?: 'movie' | 'tv') {
  return useQuery({
    queryKey: ['library', mediaType],
    queryFn: () => getLibraryItems(mediaType),
    staleTime: 60_000,
  });
}

export function useJellyfinItem(id: string) {
  return useQuery({
    queryKey: ['jellyfin-item', id],
    queryFn: () => getJellyfinItem(id),
    enabled: !!id,
    staleTime: 60_000,
  });
}

export function useStorageInfo() {
  return useQuery({
    queryKey: ['storage-info'],
    queryFn: getStorageInfo,
    staleTime: 60_000,
  });
}

export function useTVSeasons(tmdbId: number) {
  return useQuery({
    queryKey: ['tv-seasons', tmdbId],
    queryFn: () => getTVSeasons(tmdbId),
    enabled: !!tmdbId,
    staleTime: 10 * 60_000,
  });
}

export function useTVSeasonDetail(tmdbId: number, seasonNumber: number) {
  return useQuery({
    queryKey: ['tv-season-detail', tmdbId, seasonNumber],
    queryFn: () => getTVSeasonDetail(tmdbId, seasonNumber),
    enabled: !!tmdbId && seasonNumber > 0,
    staleTime: 10 * 60_000,
  });
}

export function useJellyfinLibrary(mediaType?: 'movie' | 'tv') {
  const userId = useAuthStore((s) => s.jellyfinUserId);
  return useQuery({
    queryKey: ['jellyfin-library', mediaType, userId],
    queryFn: () => getJellyfinLibrary(userId!, mediaType),
    enabled: !!userId,
    staleTime: 30_000,
  });
}

export function useQuotaInfo() {
  return useQuery({
    queryKey: ['quota-info'],
    queryFn: getQuotaInfo,
    staleTime: 60_000,
  });
}

export function useDeleteJellyfinItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteJellyfinItem(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['library'] });
      qc.invalidateQueries({ queryKey: ['jellyfin-library'] });
      qc.invalidateQueries({ queryKey: ['quota-info'] });
      qc.invalidateQueries({ queryKey: ['storage-info'] });
    },
  });
}

export function useDeleteLibraryItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: DeleteMediaRequest) => deleteLibraryItem(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['library'] });
      qc.invalidateQueries({ queryKey: ['jellyfin-library'] });
      qc.invalidateQueries({ queryKey: ['quota-info'] });
      qc.invalidateQueries({ queryKey: ['storage-info'] });
    },
  });
}

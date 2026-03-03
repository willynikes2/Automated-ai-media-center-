import { agentApi, jellyfinApi } from './client';

export interface TMDBResult {
  id: number;
  title?: string;
  name?: string;
  overview: string;
  poster_path: string | null;
  backdrop_path: string | null;
  vote_average: number;
  release_date?: string;
  first_air_date?: string;
  media_type?: string;
  genre_ids: number[];
}

interface TMDBResponse {
  results: TMDBResult[];
  total_results: number;
  total_pages: number;
}

export async function searchTMDB(query: string, page = 1): Promise<TMDBResponse> {
  const res = await agentApi.get('/v1/tmdb/search', { params: { query, page } });
  return res.data;
}

export async function getTrending(type: 'movie' | 'tv' = 'movie', window: 'week' | 'day' = 'week'): Promise<TMDBResult[]> {
  const res = await agentApi.get(`/v1/tmdb/trending/${type}/${window}`);
  return res.data.results;
}

export async function getPopular(type: 'movie' | 'tv' = 'movie'): Promise<TMDBResult[]> {
  const res = await agentApi.get(`/v1/tmdb/popular/${type}`);
  return res.data.results;
}

export async function getTMDBDetail(type: 'movie' | 'tv', id: number) {
  const res = await agentApi.get(`/v1/tmdb/${type}/${id}`);
  return res.data;
}

// Jellyfin library
export async function getLatestMedia() {
  const res = await jellyfinApi.get('/Items/Latest', { params: { Limit: 20 } });
  return res.data;
}

export async function getLibraryItems(type: 'Movie' | 'Series', params: Record<string, unknown> = {}) {
  const res = await jellyfinApi.get('/Items', {
    params: {
      IncludeItemTypes: type,
      Recursive: true,
      SortBy: 'DateCreated,SortName',
      SortOrder: 'Descending',
      Limit: 50,
      Fields: 'Overview,Genres,DateCreated,MediaSources',
      ...params,
    },
  });
  return res.data;
}

export async function getJellyfinItem(id: string) {
  const res = await jellyfinApi.get(`/Items/${id}`, {
    params: { Fields: 'Overview,MediaSources,Path,Genres,DateCreated' },
  });
  return res.data;
}

export async function deleteJellyfinItem(id: string) {
  await jellyfinApi.delete(`/Items/${id}`);
}

export interface StorageInfo {
  total_gb: number;
  used_gb: number;
  free_gb: number;
  media_gb: number;
  soft_limit_pct: number;
  prune_policy: string;
}

export async function getStorageInfo(): Promise<StorageInfo> {
  const res = await agentApi.get('/v1/storage');
  return res.data;
}

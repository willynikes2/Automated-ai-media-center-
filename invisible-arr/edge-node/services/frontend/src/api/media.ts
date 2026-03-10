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

// User library (per-user, disk-based)
export interface LibraryItem {
  title: string;
  year: number | null;
  media_type: 'movie' | 'tv';
  file_path: string;
  file_name: string;
  size_bytes: number;
  folder: string;
}

export interface LibraryResponse {
  items: LibraryItem[];
  total: number;
  movies_count: number;
  tv_count: number;
}

export async function getLibraryItems(mediaType?: 'movie' | 'tv'): Promise<LibraryResponse> {
  const params: Record<string, string> = {};
  if (mediaType) params.media_type = mediaType;
  const res = await agentApi.get('/v1/library', { params });
  return res.data;
}

// Jellyfin (still used for latest/playback)
export async function getLatestMedia() {
  const res = await jellyfinApi.get('/Items/Latest', { params: { Limit: 20 } });
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

// TV season/episode data
export interface TVSeason {
  season_number: number;
  name: string;
  episode_count: number;
  air_date: string | null;
}

export interface TVEpisode {
  episode_number: number;
  name: string;
  air_date: string | null;
  overview: string;
  still_path: string | null;
  runtime: number | null;
}

export interface TVSeasonsResponse {
  seasons: TVSeason[];
  number_of_seasons: number;
}

export interface TVSeasonDetail {
  season_number: number;
  name: string;
  episodes: TVEpisode[];
}

export async function getTVSeasons(tmdbId: number): Promise<TVSeasonsResponse> {
  const res = await agentApi.get(`/v1/tmdb/tv/${tmdbId}/seasons`);
  return res.data;
}

export async function getTVSeasonDetail(tmdbId: number, seasonNumber: number): Promise<TVSeasonDetail> {
  const res = await agentApi.get(`/v1/tmdb/tv/${tmdbId}/season/${seasonNumber}`);
  return res.data;
}

export interface DeleteMediaRequest {
  file_path: string;
  media_type: 'movie' | 'tv';
  delete_scope: 'file' | 'season' | 'series';
}

export interface DeleteMediaResponse {
  freed_bytes: number;
  deleted_files: number;
}

export async function deleteLibraryItem(req: DeleteMediaRequest): Promise<DeleteMediaResponse> {
  const res = await agentApi.delete('/v1/library/item', { data: req });
  return res.data;
}

// Jellyfin library items
export interface JellyfinLibraryItem {
  Id: string;
  Name: string;
  Type: 'Movie' | 'Series';
  ProductionYear?: number;
  ImageTags?: { Primary?: string };
  BackdropImageTags?: string[];
  CommunityRating?: number;
  OfficialRating?: string;
  Overview?: string;
  MediaSources?: Array<{
    Path?: string;
    Size?: number;
    Container?: string;
    MediaStreams?: Array<{
      Type: string;
      DisplayTitle?: string;
      Width?: number;
      Height?: number;
    }>;
  }>;
  RunTimeTicks?: number;
  Genres?: string[];
  DateCreated?: string;
}

export interface JellyfinLibraryResponse {
  Items: JellyfinLibraryItem[];
  TotalRecordCount: number;
}

export async function getJellyfinLibrary(
  userId: string,
  mediaType?: 'movie' | 'tv'
): Promise<JellyfinLibraryResponse> {
  const includeTypes = mediaType === 'movie' ? 'Movie' : mediaType === 'tv' ? 'Series' : 'Movie,Series';
  const res = await jellyfinApi.get(`/Users/${userId}/Items`, {
    params: {
      IncludeItemTypes: includeTypes,
      Fields: 'Overview,MediaSources,Path,Genres,DateCreated',
      Recursive: true,
      SortBy: 'DateCreated,SortName',
      SortOrder: 'Descending',
    },
  });
  return res.data;
}

// Quota info (item-count based)
export interface QuotaInfo {
  movie_count: number;
  movie_quota: number;
  tv_count: number;
  tv_quota: number;
}

export async function getQuotaInfo(): Promise<QuotaInfo> {
  const res = await agentApi.get('/v1/library/quota');
  return res.data;
}

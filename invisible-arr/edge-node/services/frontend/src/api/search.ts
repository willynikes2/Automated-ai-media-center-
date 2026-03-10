import { agentApi } from './client';

export interface ReleaseResult {
  title: string;
  resolution: number;
  source: string;
  codec: string;
  audio: string;
  size_gb: number;
  seeders: number;
  score: number;
  info_hash: string;
  indexer: string;
  downloaders: string[];
}

export interface SearchResponse {
  query: string;
  total_raw: number;
  results: ReleaseResult[];
  downloaders_available: string[];
  storage_free_gb: number;
  recommended_index: number | null;
}

export async function searchReleases(
  query: string,
  mediaType: 'movie' | 'tv',
  year?: number,
): Promise<SearchResponse> {
  const params: Record<string, string | number> = { query, media_type: mediaType };
  if (year) params.year = year;
  const res = await agentApi.get('/v1/search/releases', { params });
  return res.data;
}

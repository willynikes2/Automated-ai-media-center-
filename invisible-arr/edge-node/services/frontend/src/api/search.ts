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
): Promise<SearchResponse> {
  const res = await agentApi.get('/v1/search/releases', {
    params: { query, media_type: mediaType },
  });
  return res.data;
}

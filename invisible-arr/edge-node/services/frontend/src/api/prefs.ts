import { agentApi } from './client';

export interface Prefs {
  max_resolution: number;
  allow_4k: boolean;
  max_movie_size_gb: number;
  max_episode_size_gb: number;
  prune_watched_after_days: number | null;
  keep_favorites: boolean;
  storage_soft_limit_percent: number;
  upgrade_policy: string;
}

export async function getPrefs(): Promise<Prefs> {
  const res = await agentApi.get('/v1/prefs');
  return res.data;
}

export async function updatePrefs(prefs: Partial<Prefs>): Promise<Prefs> {
  const res = await agentApi.post('/v1/prefs', prefs);
  return res.data;
}

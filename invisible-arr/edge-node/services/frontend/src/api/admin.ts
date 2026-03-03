import { agentApi, jellyfinApi } from './client';

export async function getAllJobs(params: { state?: string; limit?: number } = {}) {
  const res = await agentApi.get('/v1/jobs', { params: { ...params, all_users: true } });
  return res.data;
}

export async function getSystemHealth() {
  const res = await agentApi.get('/health');
  return res.data;
}

export async function getJellyfinServerInfo() {
  const res = await jellyfinApi.get('/System/Info');
  return res.data;
}

export async function getJellyfinUsers() {
  const res = await jellyfinApi.get('/Users');
  return res.data;
}

export async function getJellyfinLibraryCounts() {
  const [movies, shows] = await Promise.all([
    jellyfinApi.get('/Items/Counts', { params: { IncludeItemTypes: 'Movie' } }).catch(() => ({ data: { MovieCount: 0 } })),
    jellyfinApi.get('/Items/Counts', { params: { IncludeItemTypes: 'Series' } }).catch(() => ({ data: { SeriesCount: 0 } })),
  ]);
  return { movies: movies.data.MovieCount ?? 0, shows: shows.data.SeriesCount ?? 0 };
}

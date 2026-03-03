import axios from 'axios';
import { useAuthStore } from '@/stores/authStore';
import { Sentry } from '@/lib/sentry';

/** Last correlation ID received from the API — used by bug report. */
export let lastCorrelationId = '';

export const agentApi = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

agentApi.interceptors.request.use((config) => {
  const apiKey = useAuthStore.getState().apiKey;
  if (apiKey) config.headers['X-Api-Key'] = apiKey;
  return config;
});

agentApi.interceptors.response.use(
  (response) => {
    const cid = response.headers['x-correlation-id'];
    if (cid) {
      lastCorrelationId = cid;
      Sentry.setTag('correlation_id', cid);
    }
    return response;
  },
  (error) => {
    if (error.response) {
      const cid = error.response.headers?.['x-correlation-id'];
      if (cid) {
        lastCorrelationId = cid;
        Sentry.setTag('correlation_id', cid);
      }
      Sentry.addBreadcrumb({
        category: 'http',
        message: `${error.config?.method?.toUpperCase()} ${error.config?.url} → ${error.response.status}`,
        level: 'error',
        data: {
          status: error.response.status,
          correlation_id: cid || undefined,
        },
      });
    }
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const jellyfinApi = axios.create({
  baseURL: '/jellyfin',
});

jellyfinApi.interceptors.request.use((config) => {
  const token = useAuthStore.getState().jellyfinToken;
  if (token) config.headers['X-Emby-Token'] = token;
  return config;
});

export const iptvApi = axios.create({
  baseURL: '/iptv',
  headers: { 'Content-Type': 'application/json' },
});

iptvApi.interceptors.request.use((config) => {
  const apiKey = useAuthStore.getState().apiKey;
  if (apiKey) config.headers['X-Api-Key'] = apiKey;
  return config;
});

export const TMDB_IMG = 'https://image.tmdb.org/t/p';
export const posterUrl = (path: string | null, size = 'w342') =>
  path ? `${TMDB_IMG}/${size}${path}` : null;
export const backdropUrl = (path: string | null, size = 'w1280') =>
  path ? `${TMDB_IMG}/${size}${path}` : null;

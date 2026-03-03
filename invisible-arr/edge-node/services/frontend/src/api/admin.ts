import { agentApi, jellyfinApi } from './client';

// ── Interfaces ──────────────────────────────────────────────

export interface AdminStats {
  total_users: number;
  active_users: number;
  total_jobs: number;
  jobs_by_state: Record<string, number>;
  storage_used_gb: number;
}

export interface AdminUser {
  id: string;
  name: string;
  email: string | null;
  role: string;
  tier: string;
  is_active: boolean;
  storage_quota_gb: number;
  storage_used_gb: number;
  max_concurrent_jobs: number;
  max_requests_per_day: number;
  created_at: string;
  last_login: string | null;
}

export interface AdminUserUpdate {
  role?: string;
  tier?: string;
  is_active?: boolean;
  storage_quota_gb?: number;
  max_concurrent_jobs?: number;
  max_requests_per_day?: number;
}

export interface InviteData {
  id: string;
  code: string;
  tier: string;
  max_uses: number;
  times_used: number;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface InviteCreate {
  tier: string;
  max_uses: number;
  expires_in_days?: number;
}

export interface RDStatus {
  enabled: boolean;
  username?: string;
  type?: string;
  expiration?: string;
  points?: number;
}

// ── Admin endpoints ─────────────────────────────────────────

export async function getAdminStats(): Promise<AdminStats> {
  const res = await agentApi.get('/v1/admin/stats');
  return res.data;
}

export async function getAdminUsers(): Promise<AdminUser[]> {
  const res = await agentApi.get('/v1/admin/users');
  return res.data;
}

export async function updateAdminUser(id: string, body: AdminUserUpdate): Promise<AdminUser> {
  const res = await agentApi.put(`/v1/admin/users/${id}`, body);
  return res.data;
}

export async function deactivateUser(id: string): Promise<{ status: string }> {
  const res = await agentApi.delete(`/v1/admin/users/${id}`);
  return res.data;
}

export async function getInvites(): Promise<InviteData[]> {
  const res = await agentApi.get('/v1/admin/invites');
  return res.data;
}

export async function createInvite(body: InviteCreate): Promise<InviteData> {
  const res = await agentApi.post('/v1/admin/invites', body);
  return res.data;
}

export async function getRDStatus(): Promise<RDStatus> {
  const res = await agentApi.get('/v1/admin/rd-status');
  return res.data;
}

// ── Jobs (admin view) ───────────────────────────────────────

export async function getAllJobs(params: { state?: string; limit?: number } = {}) {
  const res = await agentApi.get('/v1/jobs', { params: { ...params, all_users: true } });
  return res.data;
}

// ── System health ───────────────────────────────────────────

export async function getSystemHealth() {
  const res = await agentApi.get('/health');
  return res.data;
}

// ── Jellyfin info ───────────────────────────────────────────

export async function getJellyfinServerInfo() {
  const res = await jellyfinApi.get('/System/Info');
  return res.data;
}

export async function getJellyfinLibraryCounts() {
  const [movies, shows] = await Promise.all([
    jellyfinApi.get('/Items/Counts', { params: { IncludeItemTypes: 'Movie' } }).catch(() => ({ data: { MovieCount: 0 } })),
    jellyfinApi.get('/Items/Counts', { params: { IncludeItemTypes: 'Series' } }).catch(() => ({ data: { SeriesCount: 0 } })),
  ]);
  return { movies: movies.data.MovieCount ?? 0, shows: shows.data.SeriesCount ?? 0 };
}

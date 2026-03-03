import { agentApi } from './client';
import type { InviteData } from './admin';

// ── Interfaces ──────────────────────────────────────────────

export interface ResellerStats {
  total_referred: number;
  active_referred: number;
  total_invites: number;
  storage_used_gb: number;
}

export interface ResellerInviteCreate {
  max_uses: number;
  expires_in_days?: number;
}

// ── Endpoints ───────────────────────────────────────────────

export async function getResellerStats(): Promise<ResellerStats> {
  const res = await agentApi.get('/v1/reseller/stats');
  return res.data;
}

export async function getResellerInvites(): Promise<InviteData[]> {
  const res = await agentApi.get('/v1/reseller/invites');
  return res.data;
}

export async function createResellerInvite(body: ResellerInviteCreate): Promise<InviteData> {
  const res = await agentApi.post('/v1/reseller/invites', body);
  return res.data;
}

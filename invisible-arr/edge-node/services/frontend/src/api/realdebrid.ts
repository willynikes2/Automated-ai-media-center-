import { agentApi } from './client';

export interface RDStatus {
  enabled: boolean;
  username?: string;
  type?: string;
  expiration?: string;
  points?: number;
}

export async function getRDStatus(): Promise<RDStatus> {
  const res = await agentApi.get('/v1/admin/rd-status');
  return res.data;
}

export interface VPNStatus {
  enabled: boolean;
  connected: boolean;
  public_ip?: string;
  provider?: string;
}

export async function getVPNStatus(): Promise<VPNStatus> {
  const res = await agentApi.get('/v1/admin/vpn-status');
  return res.data;
}

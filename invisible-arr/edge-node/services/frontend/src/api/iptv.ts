import { iptvApi } from './client';

export interface IPTVSource {
  id: string;
  m3u_url: string;
  epg_url: string | null;
  source_timezone: string;
  enabled: boolean;
  channel_count: number;
}

export interface IPTVChannel {
  id: string;
  source_id: string;
  tvg_id: string | null;
  name: string;
  preferred_name: string | null;
  logo: string | null;
  group_title: string | null;
  preferred_group: string | null;
  channel_number: number | null;
  enabled: boolean;
  stream_url: string;
}

export async function getSources(): Promise<IPTVSource[]> {
  const res = await iptvApi.get('/v1/iptv/sources');
  return res.data;
}

export async function addSource(body: { name: string; m3u_url: string; epg_url?: string }): Promise<{ source: IPTVSource; channels_imported: number }> {
  const res = await iptvApi.post('/v1/iptv/sources', body);
  return res.data;
}

export async function deleteSource(id: string): Promise<void> {
  await iptvApi.delete(`/v1/iptv/sources/${id}`);
}

export async function getChannels(params: { source_id?: string; group?: string; enabled?: boolean } = {}): Promise<IPTVChannel[]> {
  const res = await iptvApi.get('/v1/iptv/channels', { params });
  return res.data;
}

export async function bulkUpdateChannels(updates: { id: string; enabled?: boolean; preferred_name?: string; channel_number?: number }[]): Promise<void> {
  await iptvApi.post('/v1/iptv/channels/bulk', { updates });
}

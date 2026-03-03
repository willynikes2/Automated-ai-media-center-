import { agentApi } from './client';

export type JobState =
  | 'CREATED' | 'RESOLVING' | 'SEARCHING' | 'SELECTED'
  | 'ACQUIRING' | 'IMPORTING' | 'VERIFYING' | 'DONE' | 'FAILED';

export interface SelectedCandidate {
  title?: string;
  resolution?: number;
  source?: string;
  codec?: string;
  size_gb?: number;
  seeders?: number;
  score?: number;
}

export interface Job {
  id: string;
  user_id: string;
  tmdb_id: number | null;
  media_type: string;
  title: string;
  query: string | null;
  state: JobState;
  season: number | null;
  episode: number | null;
  selected_candidate: SelectedCandidate | null;
  rd_torrent_id: string | null;
  imported_path: string | null;
  acquisition_mode: 'download' | 'stream';
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface JobEvent {
  id: string;
  job_id: string;
  state: string;
  message: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface JobDetail extends Job {
  events: JobEvent[];
}

export async function getJobs(params: { state?: string; limit?: number } = {}): Promise<Job[]> {
  const res = await agentApi.get('/v1/jobs', { params });
  return res.data;
}

export async function getJob(id: string): Promise<JobDetail> {
  const res = await agentApi.get(`/v1/jobs/${id}`);
  return res.data;
}

export async function createRequest(body: {
  tmdb_id: number;
  media_type: 'movie' | 'tv';
  query: string;
  season?: number;
  episode?: number;
  preferred_resolution?: number;
  preferred_downloader?: 'rd' | 'torrent';
  acquisition_mode?: 'download' | 'stream';
}): Promise<Job> {
  const res = await agentApi.post('/v1/request', body);
  return res.data;
}

export async function retryJob(id: string): Promise<Job> {
  const res = await agentApi.post(`/v1/jobs/${id}/retry`);
  return res.data;
}

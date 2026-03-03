import { agentApi } from './client';

export interface BugReport {
  id: string;
  user_id: string;
  route: string;
  description: string;
  correlation_id: string | null;
  browser_info: string | null;
  status: string;
  admin_notes: string | null;
  created_at: string;
}

export interface BugReportCreate {
  route: string;
  description: string;
  correlation_id?: string;
  browser_info?: string;
}

export async function createBugReport(data: BugReportCreate): Promise<BugReport> {
  const res = await agentApi.post<BugReport>('/v1/bugs', data);
  return res.data;
}

export async function getMyBugs(): Promise<BugReport[]> {
  const res = await agentApi.get<BugReport[]>('/v1/bugs');
  return res.data;
}

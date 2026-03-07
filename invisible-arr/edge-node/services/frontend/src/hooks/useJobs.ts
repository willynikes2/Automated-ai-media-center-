import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getJobs, getJob, getJobProgress, createRequest, createBatchRequest, retryJob, cancelJob, getReleases, grabRelease, type Job } from '@/api/jobs';

export function useJobs(params: { status?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ['jobs', params],
    queryFn: () => getJobs(params),
    refetchInterval: 5000,
    staleTime: 0,
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => getJob(id),
    refetchInterval: 5000,
    staleTime: 0,
    enabled: !!id,
  });
}

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createRequest,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useBatchRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createBatchRequest,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useActiveJobs() {
  return useJobs({ limit: 50 });
}

export function useJobProgress(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['job-progress', id],
    queryFn: () => getJobProgress(id),
    refetchInterval: 3000,
    enabled,
  });
}

export function useRetryJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => retryJob(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => cancelJob(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

const TERMINAL: string[] = ['AVAILABLE', 'FAILED', 'DELETED'];
const NON_ACTIVE: string[] = ['AVAILABLE', 'FAILED', 'WAITING', 'DELETED'];
export function filterActive(jobs: Job[] | undefined) {
  return jobs?.filter((j) => !NON_ACTIVE.includes(j.state)) ?? [];
}
export function filterCompleted(jobs: Job[] | undefined) {
  return jobs?.filter((j) => TERMINAL.includes(j.state)) ?? [];
}
export function filterMonitored(jobs: Job[] | undefined) {
  return jobs?.filter((j) => j.state === 'WAITING') ?? [];
}
export function filterIssues(jobs: Job[] | undefined) {
  return jobs?.filter((j) => j.state === 'FAILED') ?? [];
}

export function useReleases(jobId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['releases', jobId],
    queryFn: () => getReleases(jobId),
    enabled,
    staleTime: 30000,
  });
}

export function useGrabRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, guid, indexerId }: { jobId: string; guid: string; indexerId: number }) =>
      grabRelease(jobId, guid, indexerId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

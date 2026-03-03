import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getJobs, getJob, createRequest, type Job } from '@/api/jobs';

export function useJobs(params: { state?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ['jobs', params],
    queryFn: () => getJobs(params),
    refetchInterval: 5000,
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => getJob(id),
    refetchInterval: 5000,
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

export function useActiveJobs() {
  return useJobs({ limit: 50 });
}

const TERMINAL: string[] = ['DONE', 'FAILED'];
export function filterActive(jobs: Job[] | undefined) {
  return jobs?.filter((j) => !TERMINAL.includes(j.state)) ?? [];
}
export function filterCompleted(jobs: Job[] | undefined) {
  return jobs?.filter((j) => TERMINAL.includes(j.state)) ?? [];
}

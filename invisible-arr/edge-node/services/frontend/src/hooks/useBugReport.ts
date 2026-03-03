import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createBugReport, getMyBugs, type BugReportCreate } from '@/api/bugs';

export function useCreateBugReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BugReportCreate) => createBugReport(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-bugs'] }),
  });
}

export function useMyBugs() {
  return useQuery({
    queryKey: ['my-bugs'],
    queryFn: getMyBugs,
  });
}

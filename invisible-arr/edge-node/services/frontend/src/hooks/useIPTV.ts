import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSources, addSource, deleteSource, getChannels, bulkUpdateChannels } from '@/api/iptv';

export function useSources() {
  return useQuery({ queryKey: ['iptv-sources'], queryFn: getSources });
}

export function useAddSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: addSource,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['iptv-sources'] }),
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteSource,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['iptv-sources'] }),
  });
}

export function useChannels(params: { source_id?: string; group?: string } = {}) {
  return useQuery({
    queryKey: ['iptv-channels', params],
    queryFn: () => getChannels(params),
    staleTime: 30_000,
  });
}

export function useBulkUpdateChannels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: bulkUpdateChannels,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['iptv-channels'] }),
  });
}

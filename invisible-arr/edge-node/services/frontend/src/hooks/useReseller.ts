import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getResellerStats,
  getResellerInvites,
  createResellerInvite,
} from '@/api/reseller';
import type { ResellerInviteCreate } from '@/api/reseller';

export function useResellerStats() {
  return useQuery({
    queryKey: ['reseller-stats'],
    queryFn: getResellerStats,
    refetchInterval: 30_000,
  });
}

export function useResellerInvites() {
  return useQuery({
    queryKey: ['reseller-invites'],
    queryFn: getResellerInvites,
    staleTime: 30_000,
  });
}

export function useCreateResellerInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ResellerInviteCreate) => createResellerInvite(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reseller-invites'] });
      qc.invalidateQueries({ queryKey: ['reseller-stats'] });
    },
  });
}

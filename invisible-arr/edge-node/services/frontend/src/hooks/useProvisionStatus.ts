import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { provision, getProvisionStatus, type ProvisionStatus } from '@/api/auth';

export function useProvisionStatus(enabled: boolean = false) {
  return useQuery({
    queryKey: ['provisionStatus'],
    queryFn: getProvisionStatus,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.all_complete || data?.setup_complete) return false;
      return 1500;
    },
    enabled,
    staleTime: 0,
  });
}

export function useProvision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: provision,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['provisionStatus'] });
    },
  });
}

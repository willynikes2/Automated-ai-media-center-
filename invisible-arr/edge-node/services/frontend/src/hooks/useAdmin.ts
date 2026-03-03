import { useQuery } from '@tanstack/react-query';
import { getSystemHealth, getJellyfinServerInfo, getJellyfinUsers, getJellyfinLibraryCounts } from '@/api/admin';
import { getRDStatus } from '@/api/realdebrid';

export function useSystemHealth() {
  return useQuery({
    queryKey: ['system-health'],
    queryFn: getSystemHealth,
    refetchInterval: 15_000,
  });
}

export function useJellyfinInfo() {
  return useQuery({
    queryKey: ['jellyfin-info'],
    queryFn: getJellyfinServerInfo,
    staleTime: 60_000,
  });
}

export function useJellyfinUsers() {
  return useQuery({
    queryKey: ['jellyfin-users'],
    queryFn: getJellyfinUsers,
    staleTime: 30_000,
  });
}

export function useLibraryCounts() {
  return useQuery({
    queryKey: ['library-counts'],
    queryFn: getJellyfinLibraryCounts,
    staleTime: 60_000,
  });
}

export function useRDStatus() {
  return useQuery({
    queryKey: ['rd-status'],
    queryFn: getRDStatus,
    staleTime: 60_000,
  });
}

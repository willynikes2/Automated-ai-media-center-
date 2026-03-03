import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getSystemHealth,
  getJellyfinServerInfo,
  getJellyfinLibraryCounts,
  getAdminStats,
  getAdminUsers,
  updateAdminUser,
  deactivateUser,
  getInvites,
  createInvite,
  getRDStatus,
  getAllJobs,
} from '@/api/admin';
import type { AdminUserUpdate, InviteCreate } from '@/api/admin';

// ── System ──────────────────────────────────────────────────

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

export function useLibraryCounts() {
  return useQuery({
    queryKey: ['library-counts'],
    queryFn: getJellyfinLibraryCounts,
    staleTime: 60_000,
  });
}

// ── Admin stats ─────────────────────────────────────────────

export function useAdminStats() {
  return useQuery({
    queryKey: ['admin-stats'],
    queryFn: getAdminStats,
    refetchInterval: 30_000,
  });
}

// ── Admin users ─────────────────────────────────────────────

export function useAdminUsers() {
  return useQuery({
    queryKey: ['admin-users'],
    queryFn: getAdminUsers,
    staleTime: 30_000,
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminUserUpdate }) => updateAdminUser(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

export function useDeactivateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deactivateUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });
}

// ── Invites ─────────────────────────────────────────────────

export function useInvites() {
  return useQuery({
    queryKey: ['admin-invites'],
    queryFn: getInvites,
    staleTime: 30_000,
  });
}

export function useCreateInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: InviteCreate) => createInvite(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-invites'] }),
  });
}

// ── Real-Debrid ─────────────────────────────────────────────

export function useRDStatus() {
  return useQuery({
    queryKey: ['rd-status'],
    queryFn: getRDStatus,
    staleTime: 60_000,
  });
}

// ── Jobs (admin) ────────────────────────────────────────────

export function useAllJobs(params: { state?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ['admin-jobs', params],
    queryFn: () => getAllJobs(params),
    refetchInterval: 15_000,
  });
}

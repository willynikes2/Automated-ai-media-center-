import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { loginWithEmail, loginWithJellyfin, register, getCurrentUser } from '@/api/auth';
import type { AuthResult } from '@/api/auth';
import { useAuthStore } from '@/stores/authStore';
import type { AuthUser } from '@/stores/authStore';

/* ── Helpers ──────────────────────────────────────────────────── */

function toAuthUser(data: AuthResult): AuthUser {
  return {
    id: data.userId,
    name: data.name,
    apiKey: data.apiKey,
    email: data.email,
    role: data.role,
    tier: data.tier,
  };
}

/* ── Email login ─────────────────────────────────────────────── */

export function useEmailLogin() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      loginWithEmail(email, password),
    onSuccess: (data) => {
      login(toAuthUser(data));
      navigate('/');
    },
  });
}

/* ── Jellyfin login ──────────────────────────────────────────── */

export function useJellyfinLogin() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      loginWithJellyfin(username, password),
    onSuccess: (data) => {
      login(toAuthUser(data), data.jellyfinToken, data.jellyfinUserId);
      navigate('/');
    },
  });
}

/* ── Registration ────────────────────────────────────────────── */

export function useRegister() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({
      email,
      password,
      name,
      inviteCode,
    }: {
      email: string;
      password: string;
      name: string;
      inviteCode: string;
    }) => register(email, password, name, inviteCode),
    onSuccess: (data) => {
      login(toAuthUser(data));
      navigate('/setup');
    },
  });
}

/* ── Session check ───────────────────────────────────────────── */

export function useSessionCheck() {
  const updateUser = useAuthStore((s) => s.updateUser);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        const data = await getCurrentUser();
        updateUser({
          id: data.id,
          name: data.name,
          email: data.email,
          role: data.role,
          tier: data.tier,
        });
        return data;
      } catch {
        return null;
      }
    },
    enabled: isAuthenticated,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

/* ── Logout ──────────────────────────────────────────────────── */

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  return () => {
    logout();
    navigate('/login');
  };
}

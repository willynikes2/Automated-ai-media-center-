import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { loginWithJellyfin } from '@/api/auth';
import { useAuthStore } from '@/stores/authStore';

export function useLogin() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      loginWithJellyfin(username, password),
    onSuccess: (data) => {
      login(
        { id: data.userId, name: data.name, apiKey: data.apiKey, isAdmin: data.isAdmin },
        data.jellyfinToken,
        data.jellyfinUserId
      );
      navigate('/');
    },
  });
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  return () => {
    logout();
    navigate('/login');
  };
}

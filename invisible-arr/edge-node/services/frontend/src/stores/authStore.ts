import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface AuthUser {
  id: string;
  name: string;
  apiKey: string;
  isAdmin: boolean;
}

interface AuthState {
  user: AuthUser | null;
  apiKey: string | null;
  jellyfinToken: string | null;
  jellyfinUserId: string | null;
  isAuthenticated: boolean;
  login: (user: AuthUser, jellyfinToken: string, jellyfinUserId: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      apiKey: null,
      jellyfinToken: null,
      jellyfinUserId: null,
      isAuthenticated: false,
      login: (user, jellyfinToken, jellyfinUserId) =>
        set({
          user,
          apiKey: user.apiKey,
          jellyfinToken,
          jellyfinUserId,
          isAuthenticated: true,
        }),
      logout: () =>
        set({
          user: null,
          apiKey: null,
          jellyfinToken: null,
          jellyfinUserId: null,
          isAuthenticated: false,
        }),
    }),
    { name: 'automedia-auth' }
  )
);

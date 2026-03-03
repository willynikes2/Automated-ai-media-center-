import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type UserRole = 'admin' | 'user' | 'reseller';
export type UserTier = 'starter' | 'pro' | 'family' | 'power';

export interface AuthUser {
  id: string;
  name: string;
  email: string | null;
  apiKey: string;
  role: UserRole;
  tier: UserTier;
}

interface AuthState {
  user: AuthUser | null;
  apiKey: string | null;
  jellyfinToken: string | null;
  jellyfinUserId: string | null;
  isAuthenticated: boolean;
  login: (user: AuthUser, jellyfinToken?: string, jellyfinUserId?: string) => void;
  logout: () => void;
  updateUser: (partial: Partial<AuthUser>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      apiKey: null,
      jellyfinToken: null,
      jellyfinUserId: null,
      isAuthenticated: false,
      login: (user, jellyfinToken, jellyfinUserId) =>
        set({
          user,
          apiKey: user.apiKey,
          jellyfinToken: jellyfinToken ?? null,
          jellyfinUserId: jellyfinUserId ?? null,
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
      updateUser: (partial) => {
        const current = get().user;
        if (!current) return;
        const updated = { ...current, ...partial };
        set({
          user: updated,
          apiKey: updated.apiKey,
        });
      },
    }),
    { name: 'automedia-auth' }
  )
);

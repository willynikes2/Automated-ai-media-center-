import { agentApi, jellyfinApi } from './client';
import type { UserRole, UserTier } from '@/stores/authStore';

/* ── Jellyfin types ─────────────────────────────────────────────── */

interface JellyfinAuthResponse {
  User: {
    Id: string;
    Name: string;
    Policy: { IsAdministrator: boolean };
  };
  AccessToken: string;
}

/* ── Backend response shape (shared across login/register/jf) ─── */

interface AuthResponse {
  user_id: string;
  api_key: string;
  name: string;
  role: UserRole;
  tier: UserTier;
  setup_complete: boolean;
}

/* ── Return type for all login/register helpers ───────────────── */

export interface AuthResult {
  userId: string;
  name: string;
  apiKey: string;
  email: string | null;
  role: UserRole;
  tier: UserTier;
  setupComplete: boolean;
  jellyfinToken?: string;
  jellyfinUserId?: string;
}

/* ── Helpers ──────────────────────────────────────────────────── */

function mapAuthResponse(data: AuthResponse, extra?: { email?: string; jellyfinToken?: string; jellyfinUserId?: string }): AuthResult {
  return {
    userId: data.user_id,
    name: data.name,
    apiKey: data.api_key,
    email: extra?.email ?? null,
    role: data.role,
    tier: data.tier,
    setupComplete: data.setup_complete,
    jellyfinToken: extra?.jellyfinToken,
    jellyfinUserId: extra?.jellyfinUserId,
  };
}

/* ── Email login ─────────────────────────────────────────────── */

export async function loginWithEmail(email: string, password: string): Promise<AuthResult> {
  const res = await agentApi.post<AuthResponse>('/v1/auth/login', { email, password });
  return mapAuthResponse(res.data, { email });
}

/* ── Registration ────────────────────────────────────────────── */

export async function register(
  email: string,
  password: string,
  name: string,
  inviteCode: string,
): Promise<AuthResult> {
  const res = await agentApi.post<AuthResponse>('/v1/auth/register', {
    email,
    password,
    name,
    invite_code: inviteCode,
  });
  return mapAuthResponse(res.data, { email });
}

/* ── Jellyfin login ──────────────────────────────────────────── */

export async function loginWithJellyfin(username: string, password: string): Promise<AuthResult> {
  // Authenticate against Jellyfin
  const jfRes = await jellyfinApi.post<JellyfinAuthResponse>(
    '/Users/AuthenticateByName',
    { Username: username, Pw: password },
    {
      headers: {
        'X-Emby-Authorization':
          'MediaBrowser Client="CutDaCord", Device="PWA", DeviceId="automedia-pwa", Version="1.0.0"',
      },
    },
  );

  const jf = jfRes.data;

  // Register/login with agent-api to get our API key
  const agentRes = await agentApi.post<AuthResponse>('/v1/auth/jellyfin-login', {
    jellyfin_user_id: jf.User.Id,
    jellyfin_username: jf.User.Name,
    jellyfin_token: jf.AccessToken,
  });

  return mapAuthResponse(agentRes.data, {
    jellyfinToken: jf.AccessToken,
    jellyfinUserId: jf.User.Id,
  });
}

/* ── Google OAuth ────────────────────────────────────────────── */

export async function getGoogleAuthUrl(): Promise<string> {
  const res = await agentApi.get<{ url: string }>('/v1/auth/google/url');
  return res.data.url;
}

export async function loginWithGoogle(code: string, redirectUri: string): Promise<AuthResult> {
  const res = await agentApi.post<AuthResponse>('/v1/auth/google/callback', {
    code,
    redirect_uri: redirectUri,
  });
  return mapAuthResponse(res.data, { email: undefined });
}

/* ── Provision types ─────────────────────────────────────────── */

export interface ProvisionStatusItem {
  status: 'pending' | 'in_progress' | 'success' | 'failed';
  error?: string;
}

export interface ProvisionStatus {
  iptv: ProvisionStatusItem;
  rd: ProvisionStatusItem;
  library: ProvisionStatusItem;
  prefs: ProvisionStatusItem;
  all_complete: boolean;
  setup_complete: boolean;
}

/* ── Provision API ───────────────────────────────────────────── */

export async function provision(data: {
  rd_api_token?: string;
  preferred_resolution?: number;
  allow_4k?: boolean;
}): Promise<ProvisionStatus> {
  const { data: result } = await agentApi.post('/v1/onboarding/provision', data);
  return result;
}

export async function getProvisionStatus(): Promise<ProvisionStatus> {
  const { data: result } = await agentApi.get('/v1/onboarding/status');
  return result;
}

/* ── Setup (post-registration onboarding) ────────────────────── */

/** @deprecated Use provision() instead */
export async function submitSetup(data: {
  rd_api_token?: string;
  preferred_resolution?: number;
  allow_4k?: boolean;
}) {
  const res = await agentApi.post('/v1/auth/setup', data);
  return res.data;
}

/* ── Session check ───────────────────────────────────────────── */

export async function getCurrentUser() {
  const res = await agentApi.get('/v1/auth/me');
  return res.data;
}

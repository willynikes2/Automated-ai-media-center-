import { agentApi, jellyfinApi } from './client';

interface JellyfinAuthResponse {
  User: {
    Id: string;
    Name: string;
    Policy: { IsAdministrator: boolean };
  };
  AccessToken: string;
}

interface LoginResult {
  userId: string;
  name: string;
  apiKey: string;
  jellyfinToken: string;
  jellyfinUserId: string;
  isAdmin: boolean;
}

export async function loginWithJellyfin(username: string, password: string): Promise<LoginResult> {
  // Authenticate against Jellyfin
  const jfRes = await jellyfinApi.post<JellyfinAuthResponse>(
    '/Users/AuthenticateByName',
    { Username: username, Pw: password },
    {
      headers: {
        'X-Emby-Authorization':
          'MediaBrowser Client="AutoMedia", Device="PWA", DeviceId="automedia-pwa", Version="1.0.0"',
      },
    }
  );

  const jf = jfRes.data;

  // Register/login with agent-api to get our API key
  const agentRes = await agentApi.post('/v1/auth/login', {
    jellyfin_user_id: jf.User.Id,
    jellyfin_username: jf.User.Name,
    jellyfin_token: jf.AccessToken,
    is_admin: jf.User.Policy.IsAdministrator,
  });

  return {
    userId: agentRes.data.user_id,
    name: jf.User.Name,
    apiKey: agentRes.data.api_key,
    jellyfinToken: jf.AccessToken,
    jellyfinUserId: jf.User.Id,
    isAdmin: jf.User.Policy.IsAdministrator,
  };
}

export async function getCurrentUser() {
  const res = await agentApi.get('/v1/auth/me');
  return res.data;
}

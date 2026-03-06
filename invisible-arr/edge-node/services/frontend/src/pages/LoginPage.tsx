import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Scissors } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useEmailLogin, useJellyfinLogin } from '@/hooks/useAuth';
import { getGoogleAuthUrl } from '@/api/auth';

type LoginTab = 'email' | 'jellyfin';

export function LoginPage() {
  const [activeTab, setActiveTab] = useState<LoginTab>('email');

  // Email form state
  const [email, setEmail] = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const emailLogin = useEmailLogin();

  // Jellyfin form state
  const [username, setUsername] = useState('');
  const [jellyfinPassword, setJellyfinPassword] = useState('');
  const jellyfinLogin = useJellyfinLogin();

  const [googleLoading, setGoogleLoading] = useState(false);

  const activeMutation = activeTab === 'email' ? emailLogin : jellyfinLogin;

  const handleGoogleLogin = async () => {
    try {
      setGoogleLoading(true);
      const url = await getGoogleAuthUrl();
      window.location.href = url;
    } catch {
      setGoogleLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (activeTab === 'email') {
      emailLogin.mutate({ email, password: emailPassword });
    } else {
      jellyfinLogin.mutate({ username, password: jellyfinPassword });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 bg-bg-primary">
        <div className="absolute inset-0 bg-gradient-to-br from-accent/5 via-transparent to-purple-900/10" />
        <div className="absolute top-1/4 -left-1/4 w-96 h-96 rounded-full bg-accent/5 blur-3xl" />
        <div className="absolute bottom-1/4 -right-1/4 w-96 h-96 rounded-full bg-purple-600/5 blur-3xl" />
      </div>

      {/* Login card */}
      <div className="glass relative z-10 w-full max-w-sm rounded-2xl p-8">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
            <Scissors className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">CutDaCord.app</h1>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/10 mb-6">
          <button
            type="button"
            onClick={() => setActiveTab('email')}
            className={`flex-1 pb-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === 'email'
                ? 'text-accent border-accent'
                : 'text-text-tertiary border-transparent hover:text-text-secondary'
            }`}
          >
            Email
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('jellyfin')}
            className={`flex-1 pb-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === 'jellyfin'
                ? 'text-accent border-accent'
                : 'text-text-tertiary border-transparent hover:text-text-secondary'
            }`}
          >
            Media Server
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {activeTab === 'email' ? (
            <>
              <Input
                label="Username or Email"
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="username or email"
                autoComplete="username"
                autoFocus
              />
              <Input
                label="Password"
                type="password"
                value={emailPassword}
                onChange={(e) => setEmailPassword(e.target.value)}
                placeholder="Your password"
                autoComplete="current-password"
              />
            </>
          ) : (
            <>
              <Input
                label="Username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Your media server username"
                autoComplete="username"
                autoFocus
              />
              <Input
                label="Password"
                type="password"
                value={jellyfinPassword}
                onChange={(e) => setJellyfinPassword(e.target.value)}
                placeholder="Your media server password"
                autoComplete="current-password"
              />
            </>
          )}

          {activeMutation.isError && (
            <p className="text-sm text-status-failed">
              {(activeMutation.error as any)?.response?.status === 401
                ? 'Invalid credentials'
                : 'Login failed. Check your connection.'}
            </p>
          )}

          <Button type="submit" className="w-full" size="lg" loading={activeMutation.isPending}>
            Sign In
          </Button>
        </form>

        {/* Social login divider */}
        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/10" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="px-2 bg-bg-secondary text-text-tertiary">or continue with</span>
          </div>
        </div>

        {/* Social login buttons */}
        <div className="space-y-3">
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={googleLoading}
            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 transition-colors text-sm font-medium disabled:opacity-50"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            {googleLoading ? 'Redirecting...' : 'Google'}
          </button>
        </div>

        <div className="mt-6 text-center space-y-3">
          <Link to="/quick-connect" className="block text-sm text-accent hover:text-accent-hover transition-colors">
            Set up a device with Quick Connect
          </Link>
          <Link to="/register" className="block text-sm text-text-secondary hover:text-text-primary transition-colors">
            Don't have an account? <span className="text-accent hover:text-accent-hover">Register with invite code</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

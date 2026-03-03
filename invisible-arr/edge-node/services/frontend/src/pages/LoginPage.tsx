import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Scissors } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useEmailLogin, useJellyfinLogin } from '@/hooks/useAuth';

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

  const activeMutation = activeTab === 'email' ? emailLogin : jellyfinLogin;

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
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
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

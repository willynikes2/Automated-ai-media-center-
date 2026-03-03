import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Zap } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useLogin } from '@/hooks/useAuth';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const loginMutation = useLogin();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loginMutation.mutate({ username, password });
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
            <Zap className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">AutoMedia</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Your Jellyfin username"
            autoComplete="username"
            autoFocus
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your Jellyfin password"
            autoComplete="current-password"
          />

          {loginMutation.isError && (
            <p className="text-sm text-status-failed">
              {(loginMutation.error as any)?.response?.status === 401
                ? 'Invalid username or password'
                : 'Login failed. Check your connection.'}
            </p>
          )}

          <Button type="submit" className="w-full" size="lg" loading={loginMutation.isPending}>
            Sign In
          </Button>
        </form>

        <div className="mt-6 text-center">
          <Link to="/quick-connect" className="text-sm text-accent hover:text-accent-hover transition-colors">
            Set up a device with Quick Connect
          </Link>
        </div>

        <p className="mt-4 text-xs text-text-tertiary text-center">
          Sign in with your Jellyfin credentials
        </p>
      </div>
    </div>
  );
}

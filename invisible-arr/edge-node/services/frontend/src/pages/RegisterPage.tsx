import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Zap } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useRegister } from '@/hooks/useAuth';

export function RegisterPage() {
  const [searchParams] = useSearchParams();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [inviteCode, setInviteCode] = useState(searchParams.get('invite') ?? '');
  const [validationError, setValidationError] = useState('');

  const registerMutation = useRegister();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError('');

    if (password.length < 8) {
      setValidationError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setValidationError('Passwords do not match.');
      return;
    }

    registerMutation.mutate({ email, password, name, inviteCode });
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 bg-bg-primary">
        <div className="absolute inset-0 bg-gradient-to-br from-accent/5 via-transparent to-purple-900/10" />
        <div className="absolute top-1/4 -left-1/4 w-96 h-96 rounded-full bg-accent/5 blur-3xl" />
        <div className="absolute bottom-1/4 -right-1/4 w-96 h-96 rounded-full bg-purple-600/5 blur-3xl" />
      </div>

      {/* Register card */}
      <div className="glass relative z-10 w-full max-w-sm rounded-2xl p-8">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
            <Zap className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">AutoMedia</h1>
        </div>

        <h2 className="text-lg font-semibold text-text-primary text-center mb-6">
          Create an account
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            autoComplete="name"
            autoFocus
            required
          />
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Min. 8 characters"
            autoComplete="new-password"
            required
          />
          <Input
            label="Confirm Password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter your password"
            autoComplete="new-password"
            required
          />
          <Input
            label="Invite Code"
            type="text"
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            placeholder="Enter your invite code"
            required
          />

          {validationError && (
            <p className="text-sm text-status-failed">{validationError}</p>
          )}

          {registerMutation.isError && (
            <p className="text-sm text-status-failed">
              {(registerMutation.error as any)?.response?.data?.detail ??
                'Registration failed. Check your invite code and try again.'}
            </p>
          )}

          <Button type="submit" className="w-full" size="lg" loading={registerMutation.isPending}>
            Create Account
          </Button>
        </form>

        <div className="mt-6 text-center">
          <Link to="/login" className="text-sm text-text-secondary hover:text-text-primary transition-colors">
            Already have an account? <span className="text-accent hover:text-accent-hover">Sign in</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

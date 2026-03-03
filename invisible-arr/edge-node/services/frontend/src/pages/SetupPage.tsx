import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Eye, EyeOff, Check, ChevronRight, ChevronLeft, ExternalLink, Zap, PartyPopper, Lock } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Toggle } from '@/components/ui/Toggle';
import { submitSetup } from '@/api/auth';
import { useAuthStore } from '@/stores/authStore';

const RESOLUTIONS = [
  { label: '480p', value: 480 },
  { label: '720p', value: 720 },
  { label: '1080p', value: 1080 },
  { label: '4K', value: 2160 },
] as const;

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={`h-2 rounded-full transition-all duration-300 ${
            i === current
              ? 'w-8 bg-accent'
              : i < current
                ? 'w-2 bg-accent/50'
                : 'w-2 bg-white/15'
          }`}
        />
      ))}
    </div>
  );
}

export function SetupPage() {
  const navigate = useNavigate();
  const tier = useAuthStore((s) => s.user?.tier ?? 'starter');

  const [step, setStep] = useState(0);

  // Step 1 state
  const [rdToken, setRdToken] = useState('');
  const [showToken, setShowToken] = useState(false);

  // Step 2 state
  const [resolution, setResolution] = useState(1080);
  const [allow4k, setAllow4k] = useState(false);

  const can4k = tier !== 'starter';

  const setupMutation = useMutation({
    mutationFn: () =>
      submitSetup({
        rd_api_token: rdToken || undefined,
        preferred_resolution: resolution,
        allow_4k: can4k ? allow4k : false,
      }),
    onSuccess: () => {
      navigate('/', { replace: true });
    },
  });

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background (matches login) */}
      <div className="absolute inset-0 bg-bg-primary">
        <div className="absolute inset-0 bg-gradient-to-br from-accent/5 via-transparent to-purple-900/10" />
        <div className="absolute top-1/4 -left-1/4 w-96 h-96 rounded-full bg-accent/5 blur-3xl" />
        <div className="absolute bottom-1/4 -right-1/4 w-96 h-96 rounded-full bg-purple-600/5 blur-3xl" />
      </div>

      {/* Wizard card */}
      <div className="glass relative z-10 w-full max-w-md rounded-2xl p-8">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-6">
          <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
            <Zap className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">AutoMedia</h1>
        </div>

        <StepIndicator current={step} total={3} />

        {/* ── Step 1: Real-Debrid ──────────────────────────────── */}
        {step === 0 && (
          <div className="space-y-5">
            <div className="text-center mb-2">
              <h2 className="text-xl font-semibold text-text-primary">Connect Real-Debrid</h2>
              <p className="text-sm text-text-secondary mt-1">
                Real-Debrid provides instant cached downloads so your media is ready in seconds instead of hours.
              </p>
            </div>

            <div className="relative">
              <Input
                label="API Token"
                type={showToken ? 'text' : 'password'}
                value={rdToken}
                onChange={(e) => setRdToken(e.target.value)}
                placeholder="Paste your Real-Debrid API token"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-3 top-[34px] text-text-tertiary hover:text-text-secondary transition-colors"
                aria-label={showToken ? 'Hide token' : 'Show token'}
              >
                {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>

            <a
              href="https://real-debrid.com/apitoken"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-accent hover:text-accent-hover transition-colors"
            >
              Get your API token from Real-Debrid
              <ExternalLink className="h-3 w-3" />
            </a>

            <div className="flex gap-3 pt-2">
              <Button
                variant="secondary"
                className="flex-1"
                onClick={() => {
                  setRdToken('');
                  setStep(1);
                }}
              >
                Skip
              </Button>
              <Button
                className="flex-1"
                onClick={() => setStep(1)}
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── Step 2: Quality Preferences ──────────────────────── */}
        {step === 1 && (
          <div className="space-y-5">
            <div className="text-center mb-2">
              <h2 className="text-xl font-semibold text-text-primary">Quality Preferences</h2>
              <p className="text-sm text-text-secondary mt-1">
                Choose your preferred resolution and quality settings.
              </p>
            </div>

            <div>
              <label className="block text-sm text-text-secondary mb-2">Preferred Resolution</label>
              <div className="grid grid-cols-4 gap-2">
                {RESOLUTIONS.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => {
                      setResolution(r.value);
                      if (r.value === 2160 && can4k) setAllow4k(true);
                    }}
                    className={`py-2.5 rounded-lg text-sm font-medium transition-all ${
                      resolution === r.value
                        ? 'bg-accent text-white shadow-lg shadow-accent/25'
                        : 'bg-bg-tertiary text-text-secondary hover:text-text-primary border border-white/10'
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Toggle
                  checked={can4k ? allow4k : false}
                  onChange={(val) => can4k && setAllow4k(val)}
                  label="Allow 4K downloads"
                  disabled={!can4k}
                />
              </div>
              {!can4k && (
                <div className="flex items-center gap-1.5 text-xs text-text-tertiary">
                  <Lock className="h-3 w-3" />
                  <span>Upgrade to Pro or higher to enable 4K downloads</span>
                </div>
              )}
            </div>

            <div className="flex gap-3 pt-2">
              <Button
                variant="secondary"
                onClick={() => setStep(0)}
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </Button>
              <Button
                className="flex-1"
                onClick={() => setStep(2)}
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── Step 3: Done ─────────────────────────────────────── */}
        {step === 2 && (
          <div className="space-y-5">
            <div className="text-center mb-2">
              <div className="inline-flex items-center justify-center h-16 w-16 rounded-full bg-accent/15 mb-4">
                <PartyPopper className="h-8 w-8 text-accent" />
              </div>
              <h2 className="text-xl font-semibold text-text-primary">You're All Set!</h2>
              <p className="text-sm text-text-secondary mt-1">
                Here's a summary of your setup:
              </p>
            </div>

            <div className="bg-bg-tertiary/50 rounded-lg p-4 space-y-2 text-sm border border-white/5">
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Real-Debrid</span>
                <span className="flex items-center gap-1.5">
                  {rdToken ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                      <span className="text-emerald-400">Connected</span>
                    </>
                  ) : (
                    <span className="text-text-tertiary">Skipped</span>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Resolution</span>
                <span className="text-text-primary font-medium">
                  {resolution === 2160 ? '4K' : `${resolution}p`}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">4K Downloads</span>
                <span className={allow4k && can4k ? 'text-emerald-400' : 'text-text-tertiary'}>
                  {allow4k && can4k ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            </div>

            {setupMutation.isError && (
              <p className="text-sm text-status-failed text-center">
                Setup failed. Please try again.
              </p>
            )}

            <div className="flex gap-3 pt-2">
              <Button
                variant="secondary"
                onClick={() => setStep(1)}
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </Button>
              <Button
                className="flex-1"
                size="lg"
                loading={setupMutation.isPending}
                onClick={() => setupMutation.mutate()}
              >
                Start Watching
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

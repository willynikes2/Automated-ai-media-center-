import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  XCircle,
  Loader2,
  Tv,
  Shield,
  Film,
  Zap,
  Scissors,
  Lock,
  Eye,
  EyeOff,
  ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Toggle } from '@/components/ui/Toggle';
import { useAuthStore } from '@/stores/authStore';
import { useProvision, useProvisionStatus } from '@/hooks/useProvisionStatus';
import type { ProvisionStatusItem } from '@/api/auth';

/* ── Constants ──────────────────────────────────────────────────── */

const RESOLUTIONS = [
  { label: '480p', value: 480 },
  { label: '720p', value: 720 },
  { label: '1080p', value: 1080 },
  { label: '4K', value: 2160 },
] as const;

const PAID_TIERS = ['pro', 'family', 'power'] as const;

const TIER_LABELS: Record<string, string> = {
  starter: 'Starter',
  pro: 'Pro',
  family: 'Family',
  power: 'Power',
};

const TIER_FEATURES: Record<string, string[]> = {
  starter: ['HD streaming up to 1080p', 'Basic media library', 'Community support'],
  pro: ['4K Ultra HD streaming', 'Real-Debrid included', 'Priority cached downloads', 'Premium support'],
  family: ['4K Ultra HD streaming', 'Real-Debrid included', 'Up to 5 profiles', 'Family sharing', 'Priority support'],
  power: ['4K Ultra HD streaming', 'Real-Debrid included', 'Unlimited profiles', 'API access', 'Dedicated support'],
};

/* ── Provision checklist items ──────────────────────────────────── */

interface ChecklistItem {
  key: 'iptv' | 'rd' | 'library' | 'prefs';
  label: string;
  icon: typeof Tv;
}

const CHECKLIST: ChecklistItem[] = [
  { key: 'iptv', label: 'TV line', icon: Tv },
  { key: 'rd', label: 'Real-Debrid', icon: Shield },
  { key: 'library', label: 'Media library', icon: Film },
  { key: 'prefs', label: 'Catalog', icon: Zap },
];

/* ── Step Indicator ─────────────────────────────────────────────── */

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

/* ── Status icon for provisioning checklist ─────────────────────── */

function StatusIcon({ status }: { status: ProvisionStatusItem['status'] }) {
  switch (status) {
    case 'success':
      return <CheckCircle className="h-5 w-5 text-emerald-400" />;
    case 'failed':
      return <XCircle className="h-5 w-5 text-red-400" />;
    case 'in_progress':
      return <Loader2 className="h-5 w-5 text-accent animate-spin" />;
    default:
      return <div className="h-5 w-5 rounded-full border-2 border-white/20" />;
  }
}

/* ── Resolution Picker ──────────────────────────────────────────── */

function ResolutionPicker({
  resolution,
  setResolution,
  can4k,
  setAllow4k,
}: {
  resolution: number;
  setResolution: (v: number) => void;
  can4k: boolean;
  setAllow4k: (v: boolean) => void;
}) {
  return (
    <div>
      <label className="block text-sm text-text-secondary mb-2" id="res-label">
        Preferred Resolution
      </label>
      <div className="grid grid-cols-4 gap-2" role="radiogroup" aria-labelledby="res-label">
        {RESOLUTIONS.map((r) => {
          const disabled = r.value === 2160 && !can4k;
          const selected = resolution === r.value;
          return (
            <button
              key={r.value}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              onClick={() => {
                setResolution(r.value);
                if (r.value === 2160 && can4k) setAllow4k(true);
              }}
              className={`py-3 rounded-lg text-sm font-medium transition-all ${
                selected
                  ? 'bg-accent text-white shadow-lg shadow-accent/25'
                  : disabled
                    ? 'bg-bg-tertiary text-text-tertiary/50 cursor-not-allowed border border-white/5'
                    : 'bg-bg-tertiary text-text-secondary hover:text-text-primary border border-white/10'
              }`}
            >
              {r.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Quality Controls (resolution + 4K toggle) ─────────────────── */

function QualityControls({
  resolution,
  setResolution,
  allow4k,
  setAllow4k,
  can4k,
}: {
  resolution: number;
  setResolution: (v: number) => void;
  allow4k: boolean;
  setAllow4k: (v: boolean) => void;
  can4k: boolean;
}) {
  return (
    <div className="space-y-4">
      <ResolutionPicker
        resolution={resolution}
        setResolution={setResolution}
        can4k={can4k}
        setAllow4k={setAllow4k}
      />
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
            <span>Upgrade to Pro or higher to enable 4K</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Main Page ──────────────────────────────────────────────────── */

export function SetupPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const tier = user?.tier ?? 'starter';
  const isPaid = (PAID_TIERS as readonly string[]).includes(tier);

  const totalSteps = isPaid ? 2 : 3;

  const [step, setStep] = useState(0);
  const [provisionStarted, setProvisionStarted] = useState(false);

  // RD token state (free users only)
  const [rdToken, setRdToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [rdError, setRdError] = useState<string | null>(null);
  const [validatingRd, setValidatingRd] = useState(false);

  // Quality state
  const [resolution, setResolution] = useState(1080);
  const [allow4k, setAllow4k] = useState(false);
  const can4k = tier !== 'starter';

  // Provisioning
  const provisionMutation = useProvision();
  const { data: provisionData } = useProvisionStatus(provisionStarted);

  // Navigate home when setup_complete
  useEffect(() => {
    if (provisionData?.setup_complete) {
      // small delay so user can see the completed state
      const t = setTimeout(() => navigate('/', { replace: true }), 1200);
      return () => clearTimeout(t);
    }
  }, [provisionData?.setup_complete, navigate]);

  /* ── RD token validation ───────────────────────────────────────── */

  const validateRdToken = useCallback(async (): Promise<boolean> => {
    if (!rdToken.trim()) return true; // empty = skip
    setValidatingRd(true);
    setRdError(null);
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10_000);
      const res = await fetch('https://api.real-debrid.com/rest/1.0/user', {
        headers: { Authorization: `Bearer ${rdToken.trim()}` },
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (res.status === 401) {
        setRdError('Invalid or expired API token');
        return false;
      }
      if (!res.ok) {
        setRdError(`Real-Debrid API error (${res.status})`);
        return false;
      }
      return true;
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setRdError('Connection timed out. Please check your network.');
      } else {
        setRdError('Network error. Please try again.');
      }
      return false;
    } finally {
      setValidatingRd(false);
    }
  }, [rdToken]);

  /* ── Start provisioning ────────────────────────────────────────── */

  const startProvisioning = useCallback(() => {
    setProvisionStarted(true);
    provisionMutation.mutate({
      rd_api_token: rdToken.trim() || undefined,
      preferred_resolution: resolution,
      allow_4k: can4k ? allow4k : false,
    });
  }, [rdToken, resolution, allow4k, can4k, provisionMutation]);

  /* ── Step navigation ───────────────────────────────────────────── */

  const goNext = useCallback(async () => {
    // For free users on step 0, validate RD token before advancing
    if (!isPaid && step === 0 && rdToken.trim()) {
      const valid = await validateRdToken();
      if (!valid) return;
    }

    const nextStep = step + 1;
    const finalStep = totalSteps - 1;

    if (nextStep === finalStep) {
      setStep(nextStep);
      startProvisioning();
    } else {
      setStep(nextStep);
    }
  }, [step, isPaid, rdToken, validateRdToken, totalSteps, startProvisioning]);

  const goBack = useCallback(() => {
    if (provisionStarted) return;
    setStep((s) => Math.max(0, s - 1));
  }, [provisionStarted]);

  /* ── Render helpers ────────────────────────────────────────────── */

  const isProvisionStep = step === totalSteps - 1;

  // Stagger visibility for provision items
  const [visibleItems, setVisibleItems] = useState(0);
  useEffect(() => {
    if (!isProvisionStep) {
      setVisibleItems(0);
      return;
    }
    let count = 0;
    const interval = setInterval(() => {
      count++;
      setVisibleItems(count);
      if (count >= CHECKLIST.length) clearInterval(interval);
    }, 200);
    return () => clearInterval(interval);
  }, [isProvisionStep]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background */}
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
            <Scissors className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">CutDaCord.app</h1>
        </div>

        <StepIndicator current={step} total={totalSteps} />

        {/* ── Step 0: Welcome ──────────────────────────────────────── */}
        {step === 0 && (
          <div className="space-y-5">
            <div className="text-center mb-2">
              <h2 className="text-xl font-semibold text-text-primary">
                Welcome to{' '}
                <span className="text-violet-400">{TIER_LABELS[tier] ?? tier}</span>
              </h2>
              <p className="text-sm text-text-secondary mt-1">
                Let's get your media center set up.
              </p>
            </div>

            {/* Feature checklist */}
            <ul className="space-y-2">
              {(TIER_FEATURES[tier] ?? TIER_FEATURES.starter).map((feat) => (
                <li key={feat} className="flex items-center gap-2 text-sm text-text-secondary">
                  <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
                  {feat}
                </li>
              ))}
            </ul>

            {/* Paid: RD included badge + quality prefs */}
            {isPaid && (
              <>
                <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2 text-sm text-emerald-400">
                  <Shield className="h-4 w-4 shrink-0" />
                  Real-Debrid: Included
                </div>

                <QualityControls
                  resolution={resolution}
                  setResolution={setResolution}
                  allow4k={allow4k}
                  setAllow4k={setAllow4k}
                  can4k={can4k}
                />
              </>
            )}

            {/* Free: RD token input */}
            {!isPaid && (
              <>
                <div className="relative">
                  <Input
                    label="Real-Debrid API Token (optional)"
                    type={showToken ? 'text' : 'password'}
                    value={rdToken}
                    onChange={(e) => {
                      setRdToken(e.target.value);
                      setRdError(null);
                    }}
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

                {rdError && (
                  <p className="text-sm text-red-400">{rdError}</p>
                )}

                <a
                  href="https://real-debrid.com/apitoken"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-accent hover:text-accent-hover transition-colors"
                >
                  Get your API token from Real-Debrid
                  <ExternalLink className="h-3 w-3" />
                </a>
              </>
            )}

            <div className="flex gap-3 pt-2">
              {!isPaid && (
                <Button
                  variant="secondary"
                  className="flex-1"
                  onClick={() => {
                    setRdToken('');
                    setRdError(null);
                    setStep(1);
                  }}
                >
                  Skip
                </Button>
              )}
              <Button
                className="flex-1"
                loading={validatingRd}
                onClick={goNext}
              >
                {isPaid ? 'Set Up' : 'Next'}
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── Step 1: Quality (free users only) ────────────────────── */}
        {!isPaid && step === 1 && (
          <div className="space-y-5">
            <div className="text-center mb-2">
              <h2 className="text-xl font-semibold text-text-primary">Quality Preferences</h2>
              <p className="text-sm text-text-secondary mt-1">
                Choose your preferred resolution and quality settings.
              </p>
            </div>

            <QualityControls
              resolution={resolution}
              setResolution={setResolution}
              allow4k={allow4k}
              setAllow4k={setAllow4k}
              can4k={can4k}
            />

            <div className="flex gap-3 pt-2">
              <Button variant="secondary" onClick={goBack}>
                <ChevronLeft className="h-4 w-4" />
                Back
              </Button>
              <Button className="flex-1" onClick={goNext}>
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── Final Step: Provisioning Status ──────────────────────── */}
        {isProvisionStep && (
          <div className="space-y-5">
            <div className="text-center mb-2">
              <h2 className="text-xl font-semibold text-text-primary">Setting Up Your Account</h2>
              <p className="text-sm text-text-secondary mt-1">
                Configuring your media center...
              </p>
            </div>

            <div className="space-y-3" aria-live="polite">
              {CHECKLIST.map((item, i) => {
                const status: ProvisionStatusItem['status'] =
                  provisionData?.[item.key]?.status ?? 'pending';
                const isIptvWarning = item.key === 'iptv' && status === 'failed';
                const visible = i < visibleItems;

                return (
                  <div
                    key={item.key}
                    className={`flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary/50 border transition-all duration-300 ${
                      visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
                    } ${
                      isIptvWarning
                        ? 'border-amber-500/30'
                        : status === 'failed'
                          ? 'border-red-500/30'
                          : status === 'success'
                            ? 'border-emerald-500/20'
                            : 'border-white/5'
                    }`}
                  >
                    <item.icon className="h-4 w-4 text-text-tertiary shrink-0" />
                    <span className="flex-1 text-sm text-text-secondary">{item.label}</span>
                    <StatusIcon status={status} />
                  </div>
                );
              })}
            </div>

            {/* IPTV failure: amber non-blocking warning */}
            {provisionData?.iptv?.status === 'failed' && (
              <p className="text-xs text-amber-400">
                TV line setup had an issue but your account is ready. You can configure IPTV later.
              </p>
            )}

            {/* Non-IPTV failure */}
            {provisionMutation.isError && (
              <p className="text-sm text-red-400 text-center">
                Provisioning failed. Please try again.
              </p>
            )}

            <div className="flex gap-3 pt-2">
              <Button
                variant="secondary"
                onClick={goBack}
                disabled={provisionStarted}
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </Button>
              {provisionData?.setup_complete ? (
                <Button
                  className="flex-1"
                  size="lg"
                  onClick={() => navigate('/', { replace: true })}
                >
                  Start Watching
                </Button>
              ) : (
                <Button
                  className="flex-1"
                  disabled
                  loading={provisionStarted && !provisionData?.setup_complete}
                >
                  Setting up...
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

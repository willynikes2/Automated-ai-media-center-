"use client";

import { useEffect, useState } from "react";
import { Save, Loader2 } from "lucide-react";
import { getPrefs, updatePrefs, type Prefs } from "@/lib/api";

const defaults: Prefs = {
  max_resolution: 1080,
  allow_4k: false,
  max_movie_size_gb: 15,
  max_episode_size_gb: 4,
  prune_watched_after_days: 30,
  keep_favorites: true,
  storage_soft_limit_percent: 85,
  upgrade_policy: "never",
};

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<Prefs>(defaults);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getPrefs()
      .then(setPrefs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await updatePrefs(prefs);
      setPrefs(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="p-8 text-center text-gray-500">Loading settings...</div>
    );
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">Settings</h2>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Save size={16} />
          )}
          {saved ? "Saved!" : "Save"}
        </button>
      </div>

      <div className="space-y-6">
        <Section title="Quality">
          <NumberField
            label="Max Resolution"
            value={prefs.max_resolution}
            onChange={(v) => setPrefs({ ...prefs, max_resolution: v })}
            suffix="p"
          />
          <Toggle
            label="Allow 4K"
            value={prefs.allow_4k}
            onChange={(v) => setPrefs({ ...prefs, allow_4k: v })}
          />
          <NumberField
            label="Max Movie Size"
            value={prefs.max_movie_size_gb}
            onChange={(v) => setPrefs({ ...prefs, max_movie_size_gb: v })}
            suffix="GB"
          />
          <NumberField
            label="Max Episode Size"
            value={prefs.max_episode_size_gb}
            onChange={(v) => setPrefs({ ...prefs, max_episode_size_gb: v })}
            suffix="GB"
          />
        </Section>

        <Section title="Storage">
          <NumberField
            label="Prune Watched After"
            value={prefs.prune_watched_after_days}
            onChange={(v) =>
              setPrefs({ ...prefs, prune_watched_after_days: v })
            }
            suffix="days"
          />
          <Toggle
            label="Keep Favorites"
            value={prefs.keep_favorites}
            onChange={(v) => setPrefs({ ...prefs, keep_favorites: v })}
          />
          <NumberField
            label="Storage Soft Limit"
            value={prefs.storage_soft_limit_percent}
            onChange={(v) =>
              setPrefs({ ...prefs, storage_soft_limit_percent: v })
            }
            suffix="%"
          />
        </Section>

        <Section title="Upgrades">
          <SelectField
            label="Upgrade Policy"
            value={prefs.upgrade_policy}
            options={["never", "quality", "always"]}
            onChange={(v) => setPrefs({ ...prefs, upgrade_policy: v })}
          />
        </Section>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-surface-800 rounded-xl border border-surface-600 p-6">
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        {title}
      </h3>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  suffix?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <label className="text-sm text-gray-300">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-24 bg-surface-700 border border-surface-600 rounded-lg px-3 py-1.5 text-sm text-white text-right focus:outline-none focus:border-brand-500"
        />
        {suffix && <span className="text-xs text-gray-500">{suffix}</span>}
      </div>
    </div>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <label className="text-sm text-gray-300">{label}</label>
      <button
        onClick={() => onChange(!value)}
        className={`w-11 h-6 rounded-full transition-colors relative ${
          value ? "bg-brand-600" : "bg-surface-600"
        }`}
      >
        <div
          className={`w-4 h-4 rounded-full bg-white absolute top-1 transition-transform ${
            value ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </button>
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <label className="text-sm text-gray-300">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-surface-700 border border-surface-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-500"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt.charAt(0).toUpperCase() + opt.slice(1)}
          </option>
        ))}
      </select>
    </div>
  );
}

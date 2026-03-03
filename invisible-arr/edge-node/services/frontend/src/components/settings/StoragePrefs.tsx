import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPrefs, updatePrefs, type Prefs } from '@/api/prefs';
import { Toggle } from '@/components/ui/Toggle';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Card } from '@/components/ui/Card';
import { toast } from '@/components/ui/Toast';

export function StoragePrefs() {
  const qc = useQueryClient();
  const { data: prefs } = useQuery({ queryKey: ['prefs'], queryFn: getPrefs });
  const mutation = useMutation({
    mutationFn: updatePrefs,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prefs'] });
      toast('Preferences saved', 'success');
    },
  });

  const update = (patch: Partial<Prefs>) => mutation.mutate(patch);

  if (!prefs) return null;

  return (
    <Card className="p-5 space-y-5">
      <h3 className="font-semibold">Storage & Retention</h3>

      <Input
        label="Prune watched media after (days)"
        type="number"
        value={prefs.prune_watched_after_days ?? ''}
        onChange={(e) => update({ prune_watched_after_days: e.target.value ? Number(e.target.value) : null })}
        placeholder="Never"
        min={1}
      />

      <Toggle
        checked={prefs.keep_favorites}
        onChange={(v) => update({ keep_favorites: v })}
        label="Keep favorited media forever"
      />

      <Input
        label="Storage soft limit (%)"
        type="number"
        value={prefs.storage_soft_limit_percent}
        onChange={(e) => update({ storage_soft_limit_percent: Number(e.target.value) })}
        min={50}
        max={99}
      />

      <Select
        label="Upgrade Policy"
        value={prefs.upgrade_policy}
        onChange={(e) => update({ upgrade_policy: e.target.value })}
        options={[
          { value: 'never', label: 'Never upgrade' },
          { value: 'notify', label: 'Notify when better available' },
          { value: 'auto', label: 'Auto-upgrade quality' },
        ]}
      />
    </Card>
  );
}

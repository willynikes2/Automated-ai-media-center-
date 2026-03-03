import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPrefs, updatePrefs, type Prefs } from '@/api/prefs';
import { Select } from '@/components/ui/Select';
import { Toggle } from '@/components/ui/Toggle';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';
import { toast } from '@/components/ui/Toast';

export function QualityPrefs() {
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
      <h3 className="font-semibold">Quality Preferences</h3>

      <Select
        label="Max Resolution"
        value={String(prefs.max_resolution)}
        onChange={(e) => update({ max_resolution: Number(e.target.value) })}
        options={[
          { value: '480', label: '480p' },
          { value: '720', label: '720p' },
          { value: '1080', label: '1080p' },
          { value: '2160', label: '4K (2160p)' },
        ]}
      />

      <Toggle
        checked={prefs.allow_4k}
        onChange={(v) => update({ allow_4k: v })}
        label="Allow 4K downloads"
      />

      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Max Movie Size (GB)"
          type="number"
          value={prefs.max_movie_size_gb}
          onChange={(e) => update({ max_movie_size_gb: Number(e.target.value) })}
          min={1}
          max={100}
        />
        <Input
          label="Max Episode Size (GB)"
          type="number"
          value={prefs.max_episode_size_gb}
          onChange={(e) => update({ max_episode_size_gb: Number(e.target.value) })}
          min={0.5}
          max={20}
          step={0.5}
        />
      </div>
    </Card>
  );
}

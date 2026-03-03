import { useState } from 'react';
import { Plus, Trash2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card } from '@/components/ui/Card';
import { Modal } from '@/components/ui/Modal';
import { toast } from '@/components/ui/Toast';
import { useSources, useAddSource, useDeleteSource } from '@/hooks/useIPTV';

export function SourceManager() {
  const { data: sources, isLoading } = useSources();
  const addMutation = useAddSource();
  const deleteMutation = useDeleteSource();
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [m3uUrl, setM3uUrl] = useState('');
  const [epgUrl, setEpgUrl] = useState('');

  const handleAdd = () => {
    addMutation.mutate(
      { name, m3u_url: m3uUrl, epg_url: epgUrl || undefined },
      {
        onSuccess: (data) => {
          toast(`Added source with ${data.channels_imported} channels`, 'success');
          setShowAdd(false);
          setName(''); setM3uUrl(''); setEpgUrl('');
        },
        onError: () => toast('Failed to add source', 'error'),
      }
    );
  };

  const handleDelete = (id: string) => {
    if (!confirm('Delete this source and all its channels?')) return;
    deleteMutation.mutate(id, {
      onSuccess: () => toast('Source deleted', 'success'),
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">IPTV Sources</h3>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-4 w-4" /> Add Source
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-text-secondary">Loading...</p>
      ) : !sources?.length ? (
        <p className="text-sm text-text-secondary">No IPTV sources configured.</p>
      ) : (
        <div className="space-y-3">
          {sources.map((src) => (
            <Card key={src.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{src.m3u_url}</p>
                  <p className="text-xs text-text-tertiary mt-1">
                    {src.channel_count} channels · {src.enabled ? 'Enabled' : 'Disabled'} · TZ: {src.source_timezone}
                  </p>
                  {src.epg_url && <p className="text-xs text-text-tertiary truncate mt-0.5">EPG: {src.epg_url}</p>}
                </div>
                <button onClick={() => handleDelete(src.id)} className="p-2 rounded-lg hover:bg-bg-tertiary text-text-tertiary hover:text-status-failed">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add IPTV Source">
        <div className="space-y-4">
          <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="My IPTV Provider" />
          <Input label="M3U URL" value={m3uUrl} onChange={(e) => setM3uUrl(e.target.value)} placeholder="http://provider.com/playlist.m3u" />
          <Input label="EPG URL (optional)" value={epgUrl} onChange={(e) => setEpgUrl(e.target.value)} placeholder="http://provider.com/epg.xml" />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={handleAdd} loading={addMutation.isPending} disabled={!name || !m3uUrl}>Add Source</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

import { useState, useEffect, useRef, useMemo } from 'react';
import { useChannels } from '@/hooks/useIPTV';
import { useAuthStore } from '@/stores/authStore';
import { Card } from '@/components/ui/Card';
import { Tv, Clock } from 'lucide-react';

interface Programme {
  channel: string;
  title: string;
  start: Date;
  stop: Date;
  desc?: string;
}

function parseXMLTV(xml: string): { programmes: Programme[] } {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xml, 'text/xml');
  const programmes: Programme[] = [];

  doc.querySelectorAll('programme').forEach((el) => {
    const channel = el.getAttribute('channel') ?? '';
    const startStr = el.getAttribute('start') ?? '';
    const stopStr = el.getAttribute('stop') ?? '';
    const titleEl = el.querySelector('title');
    const descEl = el.querySelector('desc');

    const start = parseXMLTVTime(startStr);
    const stop = parseXMLTVTime(stopStr);
    if (!start || !stop) return;

    programmes.push({
      channel,
      title: titleEl?.textContent ?? 'Unknown',
      start,
      stop,
      desc: descEl?.textContent ?? undefined,
    });
  });

  return { programmes };
}

function parseXMLTVTime(str: string): Date | null {
  if (!str || str.length < 14) return null;
  const year = str.substring(0, 4);
  const month = str.substring(4, 6);
  const day = str.substring(6, 8);
  const hour = str.substring(8, 10);
  const min = str.substring(10, 12);
  const sec = str.substring(12, 14);
  const tz = str.substring(14).trim();
  const iso = `${year}-${month}-${day}T${hour}:${min}:${sec}${tz ? tz.replace(/(\d{2})(\d{2})/, '$1:$2') : 'Z'}`;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

const HOUR_WIDTH = 200; // px per hour
const ROW_HEIGHT = 48;
const HOURS_VISIBLE = 6;

export function EPGGuide() {
  const apiKey = useAuthStore((s) => s.apiKey);
  const { data: channels } = useChannels({ enabled: true } as any);
  const [tz, setTz] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const timezones = useMemo(() => {
    try {
      return (Intl as any).supportedValuesOf?.('timeZone') ?? ['UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Europe/London'];
    } catch {
      return ['UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Europe/London'];
    }
  }, []);

  useEffect(() => {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    fetch(`/iptv/epg.xml?user_token=${apiKey}&tz=${encodeURIComponent(tz)}`)
      .then((r) => {
        if (!r.ok) throw new Error('EPG fetch failed');
        return r.text();
      })
      .then((xml) => {
        const { programmes } = parseXMLTV(xml);
        setProgrammes(programmes);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [apiKey, tz]);

  // Scroll to current time on load
  useEffect(() => {
    if (!scrollRef.current || programmes.length === 0) return;
    const now = new Date();
    const startOfDay = new Date(now);
    startOfDay.setHours(0, 0, 0, 0);
    const hourOffset = (now.getTime() - startOfDay.getTime()) / (1000 * 60 * 60);
    scrollRef.current.scrollLeft = Math.max(0, hourOffset * HOUR_WIDTH - 100);
  }, [programmes]);

  const enabledChannels = channels?.filter((ch) => ch.enabled) ?? [];
  const now = new Date();
  const startOfDay = new Date(now);
  startOfDay.setHours(0, 0, 0, 0);

  // Build channel → programme mapping
  const channelProgrammes = useMemo(() => {
    const map = new Map<string, Programme[]>();
    for (const p of programmes) {
      const existing = map.get(p.channel) ?? [];
      existing.push(p);
      map.set(p.channel, existing);
    }
    return map;
  }, [programmes]);

  // Time header
  const hours: Date[] = [];
  for (let h = 0; h < 24; h++) {
    const d = new Date(startOfDay);
    d.setHours(h);
    hours.push(d);
  }

  const nowOffset = ((now.getTime() - startOfDay.getTime()) / (1000 * 60 * 60)) * HOUR_WIDTH;

  if (!channels?.length) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm text-text-secondary">No channels available. Add an IPTV source with an EPG URL first.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Timezone selector */}
      <div className="flex items-center gap-3">
        <Clock className="h-4 w-4 text-text-tertiary" />
        <select
          value={tz}
          onChange={(e) => setTz(e.target.value)}
          className="bg-bg-tertiary border border-white/10 rounded-lg px-3 py-1.5 text-sm text-text-primary"
        >
          {timezones.map((t: string) => (
            <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
          ))}
        </select>
        {loading && <span className="text-xs text-text-tertiary animate-pulse">Loading EPG...</span>}
        {error && <span className="text-xs text-status-failed">{error}</span>}
      </div>

      {programmes.length === 0 && !loading && (
        <Card className="p-6 text-center">
          <p className="text-sm text-text-secondary">
            No EPG data available. Make sure your IPTV sources have an EPG URL configured.
          </p>
        </Card>
      )}

      {programmes.length > 0 && (
        <div className="border border-white/5 rounded-xl overflow-hidden bg-bg-secondary">
          <div ref={scrollRef} className="overflow-x-auto overflow-y-auto max-h-[60vh]">
            <div style={{ width: 24 * HOUR_WIDTH + 160, minHeight: enabledChannels.length * ROW_HEIGHT + 40 }} className="relative">
              {/* Time header */}
              <div className="sticky top-0 z-20 flex bg-bg-secondary border-b border-white/5" style={{ height: 36 }}>
                <div className="sticky left-0 z-30 bg-bg-secondary border-r border-white/5" style={{ width: 160 }} />
                {hours.map((h, i) => (
                  <div
                    key={i}
                    className="text-[10px] text-text-tertiary flex items-center px-2 border-r border-white/5"
                    style={{ width: HOUR_WIDTH }}
                  >
                    {h.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                  </div>
                ))}
              </div>

              {/* Channel rows */}
              {enabledChannels.map((ch, rowIdx) => {
                const chProgs = channelProgrammes.get(ch.tvg_id ?? '') ?? [];

                return (
                  <div
                    key={ch.id}
                    className="flex border-b border-white/5"
                    style={{ height: ROW_HEIGHT }}
                  >
                    {/* Channel label */}
                    <div className="sticky left-0 z-10 bg-bg-secondary border-r border-white/5 flex items-center gap-2 px-2" style={{ width: 160 }}>
                      {ch.logo ? (
                        <img src={ch.logo} alt="" className="h-6 w-6 rounded object-contain shrink-0" />
                      ) : (
                        <Tv className="h-4 w-4 text-text-tertiary shrink-0" />
                      )}
                      <span className="text-[11px] truncate">{ch.preferred_name ?? ch.name}</span>
                    </div>

                    {/* Programme blocks */}
                    <div className="relative flex-1" style={{ width: 24 * HOUR_WIDTH }}>
                      {chProgs.map((p, pi) => {
                        const startHours = (p.start.getTime() - startOfDay.getTime()) / (1000 * 60 * 60);
                        const durationHours = (p.stop.getTime() - p.start.getTime()) / (1000 * 60 * 60);
                        if (startHours < 0 || startHours > 24) return null;
                        const left = startHours * HOUR_WIDTH;
                        const width = Math.max(durationHours * HOUR_WIDTH - 1, 20);
                        const isNow = now >= p.start && now < p.stop;

                        return (
                          <div
                            key={pi}
                            className={`absolute top-1 h-[calc(100%-8px)] rounded px-2 flex items-center text-[10px] truncate cursor-default ${
                              isNow
                                ? 'bg-accent/20 text-accent border border-accent/30'
                                : 'bg-bg-tertiary text-text-secondary hover:bg-bg-tertiary/80'
                            }`}
                            style={{ left, width }}
                            title={`${p.title}\n${p.start.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} - ${p.stop.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}${p.desc ? '\n' + p.desc : ''}`}
                          >
                            {p.title}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}

              {/* Current time marker */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-status-failed/70 z-10 pointer-events-none"
                style={{ left: 160 + nowOffset }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

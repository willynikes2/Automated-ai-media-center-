"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import {
  Film,
  Tv,
  CheckCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { getJobs, getJob, type Job, type JobDetail } from "@/lib/api";

const STATE_COLORS: Record<string, string> = {
  DONE: "bg-emerald-500/20 text-emerald-400",
  FAILED: "bg-red-500/20 text-red-400",
  CREATED: "bg-gray-500/20 text-gray-400",
  RESOLVING: "bg-blue-500/20 text-blue-400",
  SEARCHING: "bg-blue-500/20 text-blue-400",
  SELECTED: "bg-yellow-500/20 text-yellow-400",
  ACQUIRING: "bg-orange-500/20 text-orange-400",
  IMPORTING: "bg-purple-500/20 text-purple-400",
  VERIFYING: "bg-indigo-500/20 text-indigo-400",
};

const PIPELINE = [
  "CREATED",
  "RESOLVING",
  "SEARCHING",
  "SELECTED",
  "ACQUIRING",
  "IMPORTING",
  "VERIFYING",
  "DONE",
];

export default function ActivityPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-500">Loading...</div>}>
      <ActivityContent />
    </Suspense>
  );
}

function ActivityContent() {
  const searchParams = useSearchParams();
  const highlightId = searchParams.get("job");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(highlightId);

  const refresh = useCallback(() => {
    setLoading(true);
    getJobs(undefined, 50)
      .then(setJobs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">Activity</h2>
        <button
          onClick={refresh}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {loading && jobs.length === 0 ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : jobs.length === 0 ? (
        <div className="bg-surface-800 rounded-xl p-8 border border-surface-600 text-center text-gray-500">
          No jobs yet.
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <ActivityRow
              key={job.id}
              job={job}
              expanded={expandedId === job.id}
              onToggle={() =>
                setExpandedId(expandedId === job.id ? null : job.id)
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityRow({
  job,
  expanded,
  onToggle,
}: {
  job: Job;
  expanded: boolean;
  onToggle: () => void;
}) {
  const [detail, setDetail] = useState<JobDetail | null>(null);

  useEffect(() => {
    if (expanded && !detail) {
      getJob(job.id).then(setDetail).catch(() => {});
    }
  }, [expanded, detail, job.id]);

  const stateIdx = PIPELINE.indexOf(job.state);
  const color = STATE_COLORS[job.state] || STATE_COLORS.CREATED;

  return (
    <div className="bg-surface-800 rounded-xl border border-surface-600 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-surface-700/50 transition-colors"
      >
        {job.media_type === "movie" ? (
          <Film size={20} className="text-gray-500 flex-shrink-0" />
        ) : (
          <Tv size={20} className="text-gray-500 flex-shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-white font-medium truncate">{job.title}</p>
          <p className="text-xs text-gray-500">
            {new Date(job.created_at).toLocaleString()}
          </p>
        </div>
        <span
          className={`px-2.5 py-1 rounded-lg text-xs font-medium ${color}`}
        >
          {job.state}
        </span>
        {expanded ? (
          <ChevronUp size={16} className="text-gray-500" />
        ) : (
          <ChevronDown size={16} className="text-gray-500" />
        )}
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-surface-600">
          {/* Pipeline progress */}
          <div className="flex items-center gap-1 py-4 overflow-x-auto">
            {PIPELINE.map((step, i) => {
              const isActive = i <= stateIdx && job.state !== "FAILED";
              const isFailed = job.state === "FAILED" && step === job.state;
              return (
                <div key={step} className="flex items-center gap-1">
                  <div
                    className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap ${
                      isFailed
                        ? "bg-red-500/20 text-red-400"
                        : isActive
                          ? "bg-brand-600/30 text-brand-500"
                          : "bg-surface-700 text-gray-600"
                    }`}
                  >
                    {step === "DONE" && isActive ? (
                      <CheckCircle size={12} />
                    ) : isFailed ? (
                      <AlertCircle size={12} />
                    ) : i === stateIdx && job.state !== "DONE" ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : null}
                    {step}
                  </div>
                  {i < PIPELINE.length - 1 && (
                    <div
                      className={`w-4 h-px ${isActive ? "bg-brand-500" : "bg-surface-600"}`}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* Events timeline */}
          {detail?.events && detail.events.length > 0 && (
            <div className="space-y-2 mt-2">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                Events
              </p>
              {detail.events.map((evt) => (
                <div
                  key={evt.id}
                  className="flex items-start gap-3 text-sm"
                >
                  <span className="text-xs text-gray-600 whitespace-nowrap mt-0.5">
                    {new Date(evt.created_at).toLocaleTimeString()}
                  </span>
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${STATE_COLORS[evt.state] || STATE_COLORS.CREATED}`}
                  >
                    {evt.state}
                  </span>
                  <span className="text-gray-400 break-all">
                    {evt.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

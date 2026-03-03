"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Film, Tv, Clock, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import { getJobs, type Job } from "@/lib/api";

const STATE_COLORS: Record<string, string> = {
  DONE: "text-emerald-400",
  FAILED: "text-red-400",
  CREATED: "text-gray-400",
  RESOLVING: "text-blue-400",
  SEARCHING: "text-blue-400",
  SELECTED: "text-yellow-400",
  ACQUIRING: "text-orange-400",
  IMPORTING: "text-purple-400",
  VERIFYING: "text-indigo-400",
};

function StateIcon({ state }: { state: string }) {
  if (state === "DONE") return <CheckCircle size={16} />;
  if (state === "FAILED") return <AlertCircle size={16} />;
  return <Loader2 size={16} className="animate-spin" />;
}

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getJobs(undefined, 20)
      .then(setJobs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const active = jobs.filter((j) => j.state !== "DONE" && j.state !== "FAILED");
  const recent = jobs.filter((j) => j.state === "DONE" || j.state === "FAILED");
  const stats = {
    total: jobs.length,
    done: jobs.filter((j) => j.state === "DONE").length,
    failed: jobs.filter((j) => j.state === "FAILED").length,
    active: active.length,
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold text-white mb-6">Dashboard</h2>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: "Total Jobs", value: stats.total, color: "text-gray-300" },
          { label: "Completed", value: stats.done, color: "text-emerald-400" },
          { label: "Active", value: stats.active, color: "text-blue-400" },
          { label: "Failed", value: stats.failed, color: "text-red-400" },
        ].map((s) => (
          <div key={s.label} className="bg-surface-800 rounded-xl p-5 border border-surface-600">
            <p className="text-xs text-gray-500 uppercase tracking-wider">{s.label}</p>
            <p className={`text-3xl font-bold mt-1 ${s.color}`}>{loading ? "-" : s.value}</p>
          </div>
        ))}
      </div>

      {/* Active Jobs */}
      <section className="mb-8">
        <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <Clock size={18} /> Active Jobs
        </h3>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : active.length === 0 ? (
          <div className="bg-surface-800 rounded-xl p-6 border border-surface-600 text-center text-gray-500">
            No active jobs.{" "}
            <Link href="/search" className="text-brand-500 hover:underline">
              Search for something
            </Link>
          </div>
        ) : (
          <div className="space-y-2">
            {active.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </section>

      {/* Recent */}
      <section>
        <h3 className="text-lg font-semibold text-white mb-3">Recent</h3>
        {recent.length === 0 ? (
          <p className="text-gray-500 text-sm">Nothing yet.</p>
        ) : (
          <div className="space-y-2">
            {recent.slice(0, 10).map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function JobRow({ job }: { job: Job }) {
  const color = STATE_COLORS[job.state] || "text-gray-400";
  return (
    <Link
      href={`/activity?job=${job.id}`}
      className="flex items-center gap-4 bg-surface-800 rounded-xl px-5 py-4 border border-surface-600 hover:border-surface-500 transition-colors"
    >
      {job.media_type === "movie" ? <Film size={20} className="text-gray-500" /> : <Tv size={20} className="text-gray-500" />}
      <div className="flex-1 min-w-0">
        <p className="text-white font-medium truncate">{job.title}</p>
        <p className="text-xs text-gray-500">
          {new Date(job.created_at).toLocaleDateString()}
        </p>
      </div>
      <div className={`flex items-center gap-1.5 text-xs font-medium ${color}`}>
        <StateIcon state={job.state} />
        {job.state}
      </div>
    </Link>
  );
}

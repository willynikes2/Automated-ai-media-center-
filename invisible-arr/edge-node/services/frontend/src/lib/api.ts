const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  if (apiKey) {
    headers["X-Api-Key"] = apiKey;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...headers, ...init?.headers },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// --- Types ---

export interface Job {
  id: string;
  title: string;
  media_type: string;
  tmdb_id: number;
  state: string;
  created_at: string;
  updated_at: string;
  metadata_json?: Record<string, unknown>;
}

export interface JobDetail extends Job {
  events: JobEvent[];
}

export interface JobEvent {
  id: string;
  state: string;
  message: string;
  created_at: string;
  metadata_json?: Record<string, unknown>;
}

export interface Prefs {
  max_resolution: number;
  allow_4k: boolean;
  max_movie_size_gb: number;
  max_episode_size_gb: number;
  prune_watched_after_days: number;
  keep_favorites: boolean;
  storage_soft_limit_percent: number;
  upgrade_policy: string;
}

export interface TMDBResult {
  id: number;
  title?: string;
  name?: string;
  overview: string;
  poster_path: string | null;
  backdrop_path: string | null;
  media_type: string;
  release_date?: string;
  first_air_date?: string;
  vote_average: number;
}

// --- API calls ---

export async function getJobs(status?: string, limit = 50): Promise<Job[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  return apiFetch(`/v1/jobs?${params}`);
}

export async function getJob(id: string): Promise<JobDetail> {
  return apiFetch(`/v1/jobs/${id}`);
}

export async function createRequest(body: {
  query: string;
  media_type: string;
  tmdb_id?: number;
  season?: number;
  episode?: number;
}): Promise<Job> {
  return apiFetch("/v1/request", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getPrefs(): Promise<Prefs> {
  return apiFetch("/v1/prefs");
}

export async function updatePrefs(prefs: Partial<Prefs>): Promise<Prefs> {
  return apiFetch("/v1/prefs", {
    method: "POST",
    body: JSON.stringify(prefs),
  });
}

// TMDB search (proxied through our API or direct)
const TMDB_BASE = "https://api.themoviedb.org/3";
const TMDB_KEY = process.env.NEXT_PUBLIC_TMDB_API_KEY || "";

export async function searchTMDB(query: string): Promise<TMDBResult[]> {
  if (!TMDB_KEY) return [];
  const params = new URLSearchParams({
    api_key: TMDB_KEY,
    query,
    include_adult: "false",
  });
  const res = await fetch(`${TMDB_BASE}/search/multi?${params}`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.results || []).filter(
    (r: TMDBResult) => r.media_type === "movie" || r.media_type === "tv"
  );
}

export async function getTMDBDetail(
  mediaType: "movie" | "tv",
  id: number
): Promise<TMDBResult & Record<string, unknown>> {
  const res = await fetch(
    `${TMDB_BASE}/${mediaType}/${id}?api_key=${TMDB_KEY}`
  );
  if (!res.ok) throw new Error("TMDB fetch failed");
  return res.json();
}

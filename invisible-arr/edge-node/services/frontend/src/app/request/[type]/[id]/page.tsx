"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import { ArrowLeft, Star, Send, Loader2 } from "lucide-react";
import { getTMDBDetail, createRequest, type TMDBResult } from "@/lib/api";

export default function RequestPage() {
  const params = useParams();
  const router = useRouter();
  const mediaType = params.type as "movie" | "tv";
  const tmdbId = Number(params.id);

  const [detail, setDetail] = useState<(TMDBResult & Record<string, unknown>) | null>(null);
  const [loading, setLoading] = useState(true);
  const [requesting, setRequesting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getTMDBDetail(mediaType, tmdbId)
      .then(setDetail)
      .catch(() => setError("Failed to load details"))
      .finally(() => setLoading(false));
  }, [mediaType, tmdbId]);

  async function handleRequest() {
    if (!detail) return;
    setRequesting(true);
    setError("");
    try {
      const title = (detail.title || detail.name || "Unknown") as string;
      await createRequest({
        query: title,
        media_type: mediaType,
        tmdb_id: tmdbId,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setRequesting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        Loading...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-8 text-center text-gray-500">
        {error || "Not found"}
      </div>
    );
  }

  const title = (detail.title || detail.name || "Unknown") as string;
  const year = ((detail.release_date || detail.first_air_date || "") as string).slice(0, 4);
  const backdrop = detail.backdrop_path
    ? `https://image.tmdb.org/t/p/w1280${detail.backdrop_path}`
    : null;
  const poster = detail.poster_path
    ? `https://image.tmdb.org/t/p/w500${detail.poster_path}`
    : null;

  return (
    <div>
      {/* Backdrop */}
      <div className="relative h-72 bg-surface-700">
        {backdrop && (
          <Image
            src={backdrop}
            alt=""
            fill
            className="object-cover opacity-40"
            priority
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-surface-900 to-transparent" />
        <button
          onClick={() => router.back()}
          className="absolute top-6 left-6 flex items-center gap-2 text-sm text-gray-300 hover:text-white transition-colors z-10"
        >
          <ArrowLeft size={18} /> Back
        </button>
      </div>

      {/* Content */}
      <div className="px-8 -mt-24 relative z-10 max-w-5xl mx-auto pb-12">
        <div className="flex gap-8">
          {/* Poster */}
          <div className="flex-shrink-0 w-48 rounded-xl overflow-hidden shadow-2xl border border-surface-600">
            {poster ? (
              <Image
                src={poster}
                alt={title}
                width={192}
                height={288}
                className="object-cover w-full"
              />
            ) : (
              <div className="aspect-[2/3] bg-surface-700 flex items-center justify-center text-gray-600">
                No Poster
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 pt-24">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-3xl font-bold text-white">{title}</h1>
                <div className="flex items-center gap-3 mt-2 text-sm text-gray-400">
                  {year && <span>{year}</span>}
                  <span className="uppercase bg-surface-700 px-2 py-0.5 rounded text-xs">
                    {mediaType}
                  </span>
                  {detail.vote_average ? (
                    <span className="flex items-center gap-1">
                      <Star size={14} className="text-yellow-500" />
                      {(detail.vote_average as number).toFixed(1)}
                    </span>
                  ) : null}
                </div>
              </div>

              {/* Request button */}
              <div>
                {done ? (
                  <div className="bg-emerald-500/20 text-emerald-400 px-5 py-2.5 rounded-xl text-sm font-medium">
                    Requested!
                  </div>
                ) : (
                  <button
                    onClick={handleRequest}
                    disabled={requesting}
                    className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors"
                  >
                    {requesting ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Send size={16} />
                    )}
                    Request
                  </button>
                )}
                {error && (
                  <p className="text-red-400 text-xs mt-2">{error}</p>
                )}
              </div>
            </div>

            {detail.overview && (
              <p className="mt-4 text-gray-400 leading-relaxed max-w-2xl">
                {detail.overview}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

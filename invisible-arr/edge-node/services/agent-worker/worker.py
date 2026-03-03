"""Invisible Arr Agent Worker -- job processing pipeline.

Handles the full lifecycle: RESOLVING -> SEARCHING -> SELECTED -> ACQUIRING
-> IMPORTING -> VERIFYING (or FAILED at any step).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, update as sa_update

from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Blacklist, Job, JobEvent, JobState, Prefs
from shared.naming import movie_path, tv_path
from shared.prowlarr_client import ProwlarrClient
from shared.rd_client import RealDebridClient
from shared.redis_client import enqueue_qc
from shared.scoring import ParsedRelease, parse_release_title, score_candidate, select_best_candidate
from shared.tmdb_client import TMDBClient

logger = logging.getLogger("agent-worker.worker")

# ---------------------------------------------------------------------------
# Video file extensions considered during import
# ---------------------------------------------------------------------------
VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".ts"})


# ===========================================================================
# Helper functions
# ===========================================================================


async def get_job(job_id: str) -> Job:
    """Fetch a Job row by primary key. Raises if not found."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        # Expunge so the object is usable outside the session
        session.expunge(job)
        return job


async def get_prefs(user_id: uuid.UUID) -> Prefs | None:
    """Fetch user preferences. Returns *None* if none are configured."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Prefs).where(Prefs.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs is not None:
            session.expunge(prefs)
        return prefs


def prefs_to_dict(prefs: Prefs | None) -> dict[str, Any]:
    """Convert a Prefs ORM instance to a plain dict for the scoring engine.

    Falls back to global defaults from config when no user prefs exist.
    """
    if prefs is None:
        cfg = get_config()
        return {
            "max_resolution": cfg.default_max_resolution,
            "allow_4k": cfg.default_allow_4k,
            "max_movie_size_gb": cfg.default_max_movie_size_gb,
            "max_episode_size_gb": cfg.default_max_episode_size_gb,
        }
    return {
        "max_resolution": prefs.max_resolution,
        "allow_4k": prefs.allow_4k,
        "max_movie_size_gb": prefs.max_movie_size_gb,
        "max_episode_size_gb": prefs.max_episode_size_gb,
    }


async def transition(
    job: Job,
    new_state: JobState,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a state transition: update the job row and append a JobEvent."""
    now = datetime.utcnow()
    factory = get_session_factory()
    async with factory() as session:
        # Direct update avoids merge cascade issues with events relationship
        await session.execute(
            sa_update(Job)
            .where(Job.id == job.id)
            .values(state=new_state.value, updated_at=now)
        )

        event = JobEvent(
            job_id=job.id,
            state=new_state.value,
            message=message,
            metadata_json=metadata,
            created_at=now,
        )
        session.add(event)
        await session.commit()

        # Keep the detached object in sync
        job.state = new_state
        job.updated_at = now

    logger.info("Job %s -> %s: %s", job.id, new_state.value, message)


async def is_blacklisted(user_id: uuid.UUID, info_hash: str) -> bool:
    """Return True if *info_hash* is on the user's blacklist."""
    if not info_hash:
        return False
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Blacklist).where(
                Blacklist.user_id == user_id,
                Blacklist.release_hash == info_hash,
            )
        )
        return result.scalar_one_or_none() is not None


def get_year(job: Job) -> int:
    """Extract the year from job TMDB metadata or fall back to the current year."""
    if job.selected_candidate and isinstance(job.selected_candidate, dict):
        year = job.selected_candidate.get("year")
        if year:
            return int(year)
    return datetime.utcnow().year


# ===========================================================================
# Main pipeline
# ===========================================================================


async def process_job(job_id: str) -> None:
    """Execute the full acquisition pipeline for a single job."""
    job = await get_job(job_id)
    prefs = await get_prefs(job.user_id)
    prefs_dict = prefs_to_dict(prefs)

    # ------------------------------------------------------------------
    # 1. RESOLVING -- canonical identity via TMDB
    # ------------------------------------------------------------------
    await transition(job, JobState.RESOLVING, "Resolving TMDB identity")

    config = get_config()

    async with TMDBClient(config.tmdb_api_key) as tmdb:
        try:
            tmdb_id, canonical_title, year = await tmdb.resolve(
                job.query or job.title, job.media_type
            )
        except Exception as exc:
            await transition(job, JobState.FAILED, f"TMDB resolution failed: {exc}")
            return

    # Persist resolved identity back onto the job
    job.tmdb_id = tmdb_id
    job.title = canonical_title
    now = datetime.utcnow()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            sa_update(Job).where(Job.id == job.id).values(
                tmdb_id=tmdb_id, title=canonical_title, updated_at=now,
            )
        )
        await session.commit()
    job.updated_at = now

    logger.info("Resolved '%s' -> TMDB %d '%s' (%d)", job.query or job.title, tmdb_id, canonical_title, year)

    # ------------------------------------------------------------------
    # 2. SEARCHING -- query Prowlarr for release candidates
    # ------------------------------------------------------------------
    await transition(job, JobState.SEARCHING, f"Searching Prowlarr for: {canonical_title}")

    async with ProwlarrClient(config.prowlarr_url, config.prowlarr_api_key) as prowlarr:
        categories = [2000] if job.media_type == "movie" else [5000]

        try:
            raw_results = await prowlarr.search(
                query=f"{canonical_title} {year}",
                categories=categories,
            )
        except Exception as exc:
            await transition(job, JobState.FAILED, f"Prowlarr search failed: {exc}")
            return

    logger.info("Prowlarr returned %d results for '%s %d'", len(raw_results), canonical_title, year)

    # ------------------------------------------------------------------
    # 3. PARSE + SCORE -- build candidate list
    # ------------------------------------------------------------------
    candidates: list[ParsedRelease] = []
    for result in raw_results:
        parsed = parse_release_title(result.get("title", ""))
        parsed.size_gb = result.get("size", 0) / (1024 ** 3)
        parsed.seeders = result.get("seeders", 0)
        parsed.info_hash = result.get("infoHash", "")
        parsed.magnet_link = result.get("magnetUrl") or result.get("downloadUrl", "")
        parsed.indexer = result.get("indexer", "")

        if await is_blacklisted(job.user_id, parsed.info_hash):
            logger.debug("Skipping blacklisted release: %s", parsed.title)
            continue

        candidates.append(parsed)

    logger.info("Parsed %d candidates (%d blacklisted/skipped)", len(candidates), len(raw_results) - len(candidates))

    # ------------------------------------------------------------------
    # 4. SELECT -- pick the best candidate
    # ------------------------------------------------------------------
    # Adjust max size key based on media type
    size_key = "max_movie_size_gb" if job.media_type == "movie" else "max_episode_size_gb"
    scoring_prefs = {**prefs_dict, "max_movie_size_gb": prefs_dict.get(size_key, 15.0)}

    best = select_best_candidate(candidates, scoring_prefs)
    if best is None:
        await transition(
            job, JobState.FAILED,
            f"No valid candidates found (searched {len(raw_results)} results, {len(candidates)} after blacklist)",
        )
        return

    best_score = score_candidate(best, scoring_prefs)
    job.selected_candidate = asdict(best)
    # Stash the resolved year for import naming
    job.selected_candidate["year"] = year

    now = datetime.utcnow()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            sa_update(Job).where(Job.id == job.id).values(
                selected_candidate=job.selected_candidate, updated_at=now,
            )
        )
        await session.commit()
    job.updated_at = now

    await transition(
        job,
        JobState.SELECTED,
        f"Selected: {best.title} ({best.resolution}p, {best.source}, "
        f"{best.size_gb:.1f}GB, score={best_score})",
        metadata={"candidate": asdict(best), "score": best_score},
    )

    # ------------------------------------------------------------------
    # 5. ACQUIRE -- download via RD or VPN
    # ------------------------------------------------------------------
    await acquire(job, best, prefs_dict)


# ===========================================================================
# Acquisition
# ===========================================================================


async def acquire(
    job: Job,
    candidate: ParsedRelease,
    prefs: dict[str, Any],
) -> None:
    """Route acquisition to the appropriate backend."""
    config = get_config()

    if config.rd_enabled and config.rd_api_token:
        await acquire_via_rd(job, candidate)
    elif config.vpn_enabled:
        logger.warning("VPN torrent fallback not implemented in v1")
        await transition(
            job, JobState.FAILED,
            "VPN torrent fallback not implemented in v1",
        )
    else:
        await transition(
            job, JobState.FAILED,
            "No acquisition path available (RD disabled, VPN disabled)",
        )


def _resolve_magnet(candidate: ParsedRelease) -> str:
    """Return a magnet: URI from the candidate, constructing one from info_hash if needed."""
    link = candidate.magnet_link
    if link.startswith("magnet:"):
        return link
    # If we have an info_hash, construct a magnet URI
    if candidate.info_hash:
        return f"magnet:?xt=urn:btih:{candidate.info_hash}&dn={candidate.title}"
    # Otherwise, the link is likely a Prowlarr download redirect — return as-is
    return link


async def _resolve_download_url(url: str) -> str:
    """Follow a Prowlarr download URL to extract the actual magnet link."""
    # Don't follow redirects automatically — we need to catch magnet: redirects
    async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as http:
        resp = await http.get(url)

        # Check for redirect to magnet: URI
        if resp.is_redirect:
            location = resp.headers.get("location", "")
            if location.startswith("magnet:"):
                return location
            # Follow the redirect and try again
            resp = await http.get(location, follow_redirects=True)

        final_url = str(resp.url)
        if final_url.startswith("magnet:"):
            return final_url

        # Check response body for magnet link
        text = resp.text
        if "magnet:?" in text:
            import re
            match = re.search(r'(magnet:\?[^\s"<]+)', text)
            if match:
                return match.group(1)

    raise ValueError(f"Could not extract magnet from download URL (status={resp.status_code})")


async def acquire_via_rd(job: Job, candidate: ParsedRelease) -> None:
    """Acquire a release through Real-Debrid, download files, then import."""
    config = get_config()

    async with RealDebridClient(config.rd_api_token) as rd:
        # -- Resolve magnet link ---------------------------------------------
        magnet = _resolve_magnet(candidate)

        if not magnet.startswith("magnet:"):
            await transition(job, JobState.ACQUIRING, "Resolving download URL to magnet")
            try:
                magnet = await _resolve_download_url(magnet)
            except Exception as exc:
                await transition(job, JobState.FAILED, f"Failed to resolve download URL: {exc}")
                return

        # -- Add magnet ------------------------------------------------------
        await transition(job, JobState.ACQUIRING, "Adding magnet to Real-Debrid")

        try:
            torrent_id = await rd.add_magnet(magnet)
        except Exception as exc:
            await transition(job, JobState.FAILED, f"RD add_magnet failed: {exc}")
            return

        # Persist the RD torrent ID
        job.rd_torrent_id = torrent_id
        now = datetime.utcnow()
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                sa_update(Job).where(Job.id == job.id).values(
                    rd_torrent_id=torrent_id, updated_at=now,
                )
            )
            await session.commit()
        job.updated_at = now

        # -- Select files ----------------------------------------------------
        try:
            await rd.select_files(torrent_id, "all")
        except Exception as exc:
            await transition(job, JobState.FAILED, f"RD select_files failed: {exc}")
            return

        # -- Poll until cached/downloaded ------------------------------------
        await transition(job, JobState.ACQUIRING, "Waiting for Real-Debrid to cache/download")

        try:
            info = await rd.poll_until_ready(torrent_id, timeout=600)
        except Exception as exc:
            await transition(job, JobState.FAILED, f"RD poll timed out or failed: {exc}")
            return

        # -- Download each unrestricted link to staging ----------------------
        staging_dir = Path(config.downloads_path) / "rd" / str(job.id)
        staging_dir.mkdir(parents=True, exist_ok=True)

        links: list[str] = info.get("links", [])
        if not links:
            await transition(job, JobState.FAILED, "Real-Debrid returned no download links")
            return

        for raw_link in links:
            try:
                download_url = await rd.unrestrict_link(raw_link)
            except Exception as exc:
                logger.warning("Failed to unrestrict link %s: %s", raw_link, exc)
                continue

            filename = Path(download_url.split("/")[-1].split("?")[0]).name
            if not filename:
                logger.warning("Empty filename derived from URL %s, skipping", download_url)
                continue
            dest = staging_dir / filename

            if not dest.resolve().is_relative_to(staging_dir.resolve()):
                logger.warning("Path traversal detected for %s, skipping", filename)
                continue

            try:
                await rd.download_file(download_url, dest)
                logger.info("Downloaded %s -> %s", filename, dest)
            except Exception as exc:
                logger.warning("Failed to download %s: %s", download_url, exc)
                continue

    # -- Import to media library ---------------------------------------------
    await transition(job, JobState.IMPORTING, "Importing to media library")
    await import_files(job, staging_dir)


# ===========================================================================
# Import
# ===========================================================================


async def import_files(job: Job, staging_dir: Path) -> None:
    """Move video files from staging into the organised media library."""
    config = get_config()
    media_root = Path(config.media_path)

    video_files = [
        f for f in await asyncio.to_thread(list, staging_dir.iterdir())
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    ]

    if not video_files:
        await transition(job, JobState.FAILED, "No video files found in download")
        return

    year = get_year(job)
    imported_path: str | None = None

    for vf in video_files:
        if job.media_type == "movie":
            rel = movie_path(job.title, year, vf.suffix)
            dest = media_root / "Movies" / rel
        else:
            season = job.season if job.season is not None else 1
            episode = job.episode if job.episode is not None else 1
            rel = tv_path(job.title, season, episode, vf.suffix)
            dest = media_root / "TV" / rel

        if not dest.resolve().is_relative_to(media_root.resolve()):
            logger.warning("Path traversal detected for %s, skipping", dest)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.move, str(vf), str(dest))
        imported_path = str(dest)
        logger.info("Imported %s -> %s", vf.name, dest)

    # Persist the imported path on the job
    if imported_path is not None:
        job.imported_path = imported_path
        now = datetime.utcnow()
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                sa_update(Job).where(Job.id == job.id).values(
                    imported_path=imported_path, updated_at=now,
                )
            )
            await session.commit()
        job.updated_at = now

    # Clean up staging directory
    await asyncio.to_thread(shutil.rmtree, staging_dir, True)
    logger.info("Cleaned staging directory %s", staging_dir)

    # Enqueue QC validation
    try:
        await enqueue_qc(str(job.id))
        logger.info("Enqueued QC job for %s", job.id)
    except Exception:
        logger.exception("Failed to enqueue QC job for %s", job.id)

    await transition(
        job, JobState.VERIFYING,
        f"File imported to {imported_path}, running QC",
    )

"""Invisible Arr Agent Worker -- job processing pipeline.

Handles the full lifecycle: RESOLVING -> SEARCHING -> SELECTED -> ACQUIRING
-> IMPORTING -> VERIFYING (or FAILED at any step).
"""

from __future__ import annotations

import asyncio
import logging
import re
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
from shared.qbt_client import QBittorrentClient
from shared.rd_client import RealDebridClient
from shared.redis_client import enqueue_qc, set_download_progress, clear_download_progress
from shared.sabnzbd_client import SABnzbdClient
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


def diagnose_failure(error: Exception, candidate: ParsedRelease | None = None) -> str:
    """Map raw errors to actionable diagnostic messages."""
    error_str = str(error).lower()

    if "401" in error_str or "unauthorized" in error_str:
        return "Authentication failed — check API token/credentials."
    if "403" in error_str or "forbidden" in error_str:
        return "Access denied — account may be expired or suspended."
    if "429" in error_str or "rate limit" in error_str:
        return "Rate limited by provider. Will retry next candidate."
    if "timeout" in error_str or "timed out" in error_str:
        size_info = f" File size: {candidate.size_gb:.1f}GB." if candidate and candidate.size_gb > 0 else ""
        return f"Download timed out.{size_info} Source may be slow or unavailable."
    if "no space" in error_str or "disk full" in error_str or "errno 28" in error_str:
        return "Disk full — free space or increase storage allocation."
    if "connection" in error_str and "refused" in error_str:
        return "Could not connect to download service. Check if the service is running."
    if "404" in error_str or "not found" in error_str:
        return "File no longer available from source."
    if "503" in error_str or "502" in error_str:
        return "Download service temporarily unavailable."
    if "magnet_error" in error_str:
        return "Invalid or dead magnet link — torrent has no peers."
    if "virus" in error_str:
        return "File flagged as potentially harmful by provider."

    return f"Unexpected error: {str(error)[:200]}"


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
        parsed.protocol = result.get("protocol", "torrent").lower()

        if await is_blacklisted(job.user_id, parsed.info_hash):
            logger.debug("Skipping blacklisted release: %s", parsed.title)
            continue

        candidates.append(parsed)

    logger.info("Parsed %d candidates (%d blacklisted/skipped)", len(candidates), len(raw_results) - len(candidates))

    # ------------------------------------------------------------------
    # 4. ACQUIRE with fallback -- try top candidates
    # ------------------------------------------------------------------
    # Adjust max size key based on media type
    size_key = "max_movie_size_gb" if job.media_type == "movie" else "max_episode_size_gb"
    scoring_prefs = {**prefs_dict, "max_movie_size_gb": prefs_dict.get(size_key, 15.0)}

    scored = [(c, score_candidate(c, scoring_prefs)) for c in candidates]
    valid = sorted([(c, s) for c, s in scored if s > 0], key=lambda x: (-x[1], x[0].size_gb))

    if not valid:
        await transition(
            job, JobState.FAILED,
            f"No valid candidates found (searched {len(raw_results)} results, {len(candidates)} after blacklist)",
        )
        return

    await acquire_with_fallback(job, valid, prefs_dict, year)


# ===========================================================================
# Acquisition
# ===========================================================================


async def acquire_with_fallback(
    job: Job,
    scored_candidates: list[tuple[ParsedRelease, int]],
    prefs: dict[str, Any],
    year: int,
) -> None:
    """Try up to 3 candidates, each through available acquisition methods."""
    max_attempts = min(3, len(scored_candidates))

    for i, (candidate, score) in enumerate(scored_candidates[:max_attempts]):
        # Persist selected candidate
        job.selected_candidate = asdict(candidate)
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
            job, JobState.SELECTED,
            f"Candidate {i+1}/{max_attempts}: {candidate.title} "
            f"({candidate.resolution}p, {candidate.source}, {candidate.size_gb:.1f}GB, score={score})",
            metadata={"candidate": asdict(candidate), "score": score, "attempt": i + 1},
        )

        try:
            await acquire(job, candidate, prefs)
            return  # Success
        except Exception as exc:
            diagnosis = diagnose_failure(exc, candidate)
            await transition(
                job, JobState.ACQUIRING,
                f"Candidate {i+1} failed: {diagnosis}",
                metadata={"error": str(exc)[:500], "candidate_title": candidate.title},
            )
            if i < max_attempts - 1:
                logger.info("Trying next candidate for job %s...", job.id)
                continue

    await transition(
        job, JobState.FAILED,
        f"All {max_attempts} candidates failed. Try again later or adjust quality settings.",
    )


async def acquire(
    job: Job,
    candidate: ParsedRelease,
    prefs: dict[str, Any],
) -> None:
    """Try acquisition methods in priority order. Raises on all-method failure."""
    config = get_config()
    errors: list[str] = []

    # 1. Real-Debrid
    if config.rd_enabled and config.rd_api_token:
        try:
            if job.acquisition_mode == "stream":
                await acquire_via_rd_stream(job, candidate)
            else:
                await acquire_via_rd(job, candidate)
            await _set_acquisition_method(job, "rd")
            return
        except Exception as exc:
            msg = f"RD: {diagnose_failure(exc, candidate)}"
            errors.append(msg)
            await transition(job, JobState.ACQUIRING, msg)

    # 2. Usenet (only for Usenet protocol results from Prowlarr)
    if config.usenet_enabled and config.sabnzbd_api_key:
        if candidate.protocol == "usenet" and candidate.magnet_link:
            try:
                await acquire_via_usenet(job, candidate)
                await _set_acquisition_method(job, "usenet")
                return
            except Exception as exc:
                msg = f"Usenet: {diagnose_failure(exc, candidate)}"
                errors.append(msg)
                await transition(job, JobState.ACQUIRING, msg)

    # 3. VPN Torrent
    if config.vpn_enabled and config.qbt_password:
        try:
            await acquire_via_torrent(job, candidate)
            await _set_acquisition_method(job, "torrent")
            return
        except Exception as exc:
            msg = f"Torrent: {diagnose_failure(exc, candidate)}"
            errors.append(msg)
            await transition(job, JobState.ACQUIRING, msg)

    summary = "; ".join(errors) if errors else "No acquisition path available (all disabled)"
    raise RuntimeError(summary)


async def _set_acquisition_method(job: Job, method: str) -> None:
    """Persist which acquisition method was used."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            sa_update(Job).where(Job.id == job.id).values(acquisition_method=method)
        )
        await session.commit()


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
            match = re.search(r'(magnet:\?[^\s"<]+)', text)
            if match:
                return match.group(1)

    raise ValueError(f"Could not extract magnet from download URL (status={resp.status_code})")


async def acquire_via_rd(job: Job, candidate: ParsedRelease) -> None:
    """Acquire a release through Real-Debrid, download files, then import."""
    config = get_config()

    async with RealDebridClient(config.rd_api_token) as rd:
        magnet = _resolve_magnet(candidate)

        if not magnet.startswith("magnet:"):
            await transition(job, JobState.ACQUIRING, "Resolving download URL to magnet")
            try:
                magnet = await _resolve_download_url(magnet)
            except Exception as exc:
                raise RuntimeError(f"Failed to resolve download URL: {exc}") from exc

        await transition(job, JobState.ACQUIRING, "Adding magnet to Real-Debrid")

        try:
            torrent_id = await rd.add_magnet(magnet)
        except Exception as exc:
            raise RuntimeError(f"RD add_magnet failed: {exc}") from exc

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

        try:
            await rd.select_files(torrent_id, "all")
        except Exception as exc:
            raise RuntimeError(f"RD select_files failed: {exc}") from exc

        await transition(job, JobState.ACQUIRING, "Waiting for Real-Debrid to cache/download")

        try:
            info = await rd.poll_until_ready(torrent_id, timeout=600)
        except Exception as exc:
            raise RuntimeError(f"RD poll timed out or failed: {exc}") from exc

        # Download each unrestricted link to staging
        staging_dir = Path(config.downloads_path) / "rd" / str(job.id)
        staging_dir.mkdir(parents=True, exist_ok=True)

        links: list[str] = info.get("links", [])
        if not links:
            raise RuntimeError("Real-Debrid returned no download links")

        for idx, raw_link in enumerate(links):
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

            # Progress callback
            last_pct = [0]

            async def _on_progress(downloaded: int, total: int, _jid=str(job.id), _fn=filename, _idx=idx, _links=len(links)) -> None:
                pct = int(downloaded / total * 100) if total > 0 else 0
                if pct >= last_pct[0] + 5:
                    last_pct[0] = pct
                    await set_download_progress(_jid, pct, f"Downloading {_fn} ({_idx+1}/{_links})")

            try:
                await rd.download_file(download_url, dest, on_progress=_on_progress)
                logger.info("Downloaded %s -> %s", filename, dest)
            except Exception as exc:
                logger.warning("Failed to download %s: %s", download_url, exc)
                continue

        await clear_download_progress(str(job.id))

    # Import to media library
    await transition(job, JobState.IMPORTING, "Importing to media library")
    await import_files(job, staging_dir)


async def acquire_via_rd_stream(job: Job, candidate: ParsedRelease) -> None:
    """RD streaming mode -- unrestrict links without downloading to disk."""
    config = get_config()

    async with RealDebridClient(config.rd_api_token) as rd:
        magnet = _resolve_magnet(candidate)

        if not magnet.startswith("magnet:"):
            await transition(job, JobState.ACQUIRING, "Resolving download URL to magnet")
            magnet = await _resolve_download_url(magnet)

        await transition(job, JobState.ACQUIRING, "Adding magnet to Real-Debrid (stream mode)")
        torrent_id = await rd.add_magnet(magnet)

        now = datetime.utcnow()
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                sa_update(Job).where(Job.id == job.id).values(
                    rd_torrent_id=torrent_id, updated_at=now,
                )
            )
            await session.commit()

        await rd.select_files(torrent_id, "all")

        await transition(job, JobState.ACQUIRING, "Waiting for Real-Debrid to cache (stream mode)")
        info = await rd.poll_until_ready(torrent_id, timeout=600)

        links = info.get("links", [])
        if not links:
            raise RuntimeError("Real-Debrid returned no download links")

        streaming_urls = []
        for raw_link in links:
            url = await rd.unrestrict_link(raw_link)
            streaming_urls.append(url)

        now = datetime.utcnow()
        async with factory() as session:
            await session.execute(
                sa_update(Job).where(Job.id == job.id).values(
                    streaming_urls={"urls": streaming_urls},
                    updated_at=now,
                )
            )
            await session.commit()

    await transition(
        job, JobState.DONE,
        f"Stream ready: {len(streaming_urls)} link(s)",
        metadata={"streaming_url_count": len(streaming_urls)},
    )


async def acquire_via_usenet(job: Job, candidate: ParsedRelease) -> None:
    """Download via SABnzbd Usenet client."""
    config = get_config()

    async with SABnzbdClient(config.sabnzbd_url, config.sabnzbd_api_key) as sab:
        await transition(job, JobState.ACQUIRING, "Sending NZB to SABnzbd")

        nzo_id = await sab.add_nzb_url(
            candidate.magnet_link,
            category="automedia",
            name=candidate.title,
        )

        await transition(job, JobState.ACQUIRING, f"SABnzbd downloading (nzo={nzo_id})")
        slot = await sab.poll_until_complete(nzo_id, timeout=3600)

        storage_path = slot.get("storage", "")
        if not storage_path:
            raise RuntimeError("SABnzbd completed but reported no storage path")

    staging_dir = Path(storage_path)
    await transition(job, JobState.IMPORTING, "Importing Usenet download to media library")
    await import_files(job, staging_dir)


async def check_vpn_health() -> bool:
    """Check if Gluetun VPN tunnel is up by querying its public IP endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://gluetun:9999/v1/publicip/ip")
            if resp.status_code != 200:
                return False
            data = resp.json()
            # If Gluetun returns a public IP, the tunnel is up
            return bool(data.get("public_ip"))
    except Exception:
        return False


async def acquire_via_torrent(job: Job, candidate: ParsedRelease) -> None:
    """Download via qBittorrent behind Gluetun VPN."""
    config = get_config()

    if not await check_vpn_health():
        raise RuntimeError("VPN is not healthy — refusing torrent download for safety")

    magnet = _resolve_magnet(candidate)
    if not magnet.startswith("magnet:"):
        await transition(job, JobState.ACQUIRING, "Resolving download URL to magnet")
        magnet = await _resolve_download_url(magnet)

    save_path = f"/data/downloads/torrents/{job.id}"

    async with QBittorrentClient(config.qbt_url, config.qbt_username, config.qbt_password) as qbt:
        await transition(job, JobState.ACQUIRING, "Adding magnet to qBittorrent (VPN)")
        await qbt.add_magnet(magnet, save_path=save_path)

        await asyncio.sleep(3)  # qBittorrent needs a moment to register

        info_hash = candidate.info_hash
        if not info_hash:
            match = re.search(r'btih:([a-fA-F0-9]+)', magnet)
            if match:
                info_hash = match.group(1)
            else:
                raise RuntimeError("Cannot determine info_hash for torrent polling")

        await transition(job, JobState.ACQUIRING, "Waiting for qBittorrent download (VPN)")
        await qbt.poll_until_complete(info_hash, timeout=3600)

        await qbt.delete_torrent(info_hash, delete_files=False)

    staging_dir = Path(save_path)
    await transition(job, JobState.IMPORTING, "Importing torrent download to media library")
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

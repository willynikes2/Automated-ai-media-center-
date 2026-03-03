# Backend Download Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the download pipeline from RD-only to a multi-method acquisition system with candidate fallback, streaming links, Usenet scaffolding, VPN torrent fallback, and all public Prowlarr indexers.

**Architecture:** The worker's `acquire()` function becomes `acquire_with_fallback()` which tries up to 3 candidates, each through up to 3 acquisition methods (RD → Usenet → VPN Torrent). New clients (`qbt_client.py`, `sabnzbd_client.py`) follow the same async context manager pattern as `rd_client.py`. Download progress is tracked in Redis. A reusable shell script handles Prowlarr indexer setup.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), httpx, redis-py, Alembic, bash

---

### Task 1: Add Config Vars for Usenet + qBittorrent

**Files:**
- Modify: `services/shared/config.py:8-85`
- Modify: `.env.template`

**Step 1: Add config fields**

In `services/shared/config.py`, add after `vpn_provider` (line 35):

```python
    # qBittorrent (VPN torrent fallback)
    qbt_url: str = "http://gluetun:8080"
    qbt_username: str = "admin"
    qbt_password: str = ""

    # Usenet
    usenet_enabled: bool = False
    sabnzbd_url: str = "http://sabnzbd:8080"
    sabnzbd_api_key: str = ""
```

**Step 2: Add env vars to .env.template**

Append after the `IPTV_ENABLED=false` line:

```env
# --- Usenet (optional) ---
USENET_ENABLED=false
SABNZBD_API_KEY=

# --- qBittorrent ---
QBT_PASSWORD=
```

**Step 3: Add env vars to docker-compose agent-worker environment**

In `docker-compose.yml`, add to agent-worker environment section (after `VPN_ENABLED`):

```yaml
      - USENET_ENABLED=${USENET_ENABLED:-false}
      - SABNZBD_URL=http://sabnzbd:8080
      - SABNZBD_API_KEY=${SABNZBD_API_KEY:-}
      - QBT_URL=http://gluetun:8080
      - QBT_USERNAME=admin
      - QBT_PASSWORD=${QBT_PASSWORD:-}
```

**Step 4: Commit**

```bash
git add services/shared/config.py .env.template docker-compose.yml
git commit -m "feat: add Usenet + qBittorrent config vars"
```

---

### Task 2: DB Migration — Add streaming_urls and acquisition_method

**Files:**
- Create: `services/migrations/versions/003_add_streaming_and_method.py`
- Modify: `services/shared/models.py:80-105`

**Step 1: Create migration**

```python
"""Add streaming_urls and acquisition_method to jobs.

Revision ID: 003
Revises: 002
Create Date: 2026-03-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("streaming_urls", sa.JSON(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("acquisition_method", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "acquisition_method")
    op.drop_column("jobs", "streaming_urls")
```

**Step 2: Add fields to Job model**

In `services/shared/models.py`, after `acquisition_mode` (line 100), add:

```python
    acquisition_method: Mapped[str | None] = mapped_column(String(20), default=None)  # rd, usenet, torrent
    streaming_urls: Mapped[dict | None] = mapped_column(type_=JSON, nullable=True, default=None)
```

**Step 3: Add fields to response schemas**

In `services/shared/schemas.py`, add to `JobResponse` (after `acquisition_mode` line 73):

```python
    acquisition_method: str | None = None
    streaming_urls: dict | None = None
```

And to `JobListResponse` (after `acquisition_mode` line 95):

```python
    acquisition_method: str | None = None
    streaming_urls: dict | None = None
```

**Step 4: Update jobs router to include new fields**

In `services/agent-api/routers/jobs.py`, add `acquisition_method` and `streaming_urls` to both the `get_job` response construction (line 37-64) and the `list_jobs` response construction (line 83-102), and the `retry_job` response construction (line 139-155).

**Step 5: Run migration**

```bash
cd /home/shawn/Automated-ai-media-center-/invisible-arr/edge-node
docker compose exec agent-api alembic upgrade head
```

**Step 6: Commit**

```bash
git add services/migrations/versions/003_add_streaming_and_method.py services/shared/models.py services/shared/schemas.py services/agent-api/routers/jobs.py
git commit -m "feat: add streaming_urls and acquisition_method to Job model"
```

---

### Task 3: Download Progress Tracking

**Files:**
- Modify: `services/shared/redis_client.py`
- Modify: `services/shared/rd_client.py:166-178`
- Modify: `services/agent-api/routers/jobs.py`

**Step 1: Add Redis progress helpers**

In `services/shared/redis_client.py`, add at the end:

```python
# ---------------------------------------------------------------------------
# Download progress tracking
# ---------------------------------------------------------------------------

_PROGRESS_PREFIX = "invisiblearr:progress:"
_PROGRESS_TTL = 3600  # 1 hour


async def set_download_progress(job_id: str, percent: int, detail: str = "") -> None:
    """Store download progress for a job."""
    r = await get_redis()
    key = f"{_PROGRESS_PREFIX}{job_id}"
    await _safe_redis_op(r.hset(key, mapping={"percent": percent, "detail": detail}))
    await _safe_redis_op(r.expire(key, _PROGRESS_TTL))


async def get_download_progress(job_id: str) -> dict | None:
    """Get download progress for a job. Returns None if no progress tracked."""
    r = await get_redis()
    key = f"{_PROGRESS_PREFIX}{job_id}"
    data = await _safe_redis_op(r.hgetall(key))
    if not data:
        return None
    return {"percent": int(data.get("percent", 0)), "detail": data.get("detail", "")}


async def clear_download_progress(job_id: str) -> None:
    """Remove progress tracking for a completed job."""
    r = await get_redis()
    await _safe_redis_op(r.delete(f"{_PROGRESS_PREFIX}{job_id}"))
```

**Step 2: Add progress callback to RD download**

In `services/shared/rd_client.py`, modify `download_file` (line 166-178) to accept a progress callback:

```python
    async def download_file(
        self,
        url: str,
        dest_path: Path,
        on_progress: "Callable[[int, int], Any] | None" = None,
    ) -> None:
        """Stream-download a file from the given URL to a local path.

        Parameters
        ----------
        on_progress:
            Optional callback(downloaded_bytes, total_bytes) called every ~1MB.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading %s -> %s", url[:80], dest_path)

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as dl:
            async with dl.stream("GET", url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(dest_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 256):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total > 0:
                            on_progress(downloaded, total)

        logger.info("Download complete: %s", dest_path)
```

Add `from typing import Any, Callable` at top of rd_client.py (or use `from __future__ import annotations`).

**Step 3: Add progress endpoint**

In `services/agent-api/routers/jobs.py`, add:

```python
from shared.redis_client import get_download_progress


@router.get("/jobs/{job_id}/progress")
async def job_progress(job_id: uuid.UUID) -> dict:
    """Return download progress for an active job."""
    progress = await get_download_progress(str(job_id))
    if progress is None:
        return {"percent": -1, "detail": "No active download"}
    return progress
```

**Step 4: Commit**

```bash
git add services/shared/redis_client.py services/shared/rd_client.py services/agent-api/routers/jobs.py
git commit -m "feat: download progress tracking via Redis"
```

---

### Task 4: Error Diagnostics

**Files:**
- Modify: `services/agent-worker/worker.py`

**Step 1: Add diagnose_failure function**

Add after the helper functions section (after line 148), before the main pipeline:

```python
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
```

**Step 2: Commit**

```bash
git add services/agent-worker/worker.py
git commit -m "feat: add error diagnostics for download failures"
```

---

### Task 5: qBittorrent Client

**Files:**
- Create: `services/shared/qbt_client.py`

**Step 1: Create qbt_client.py**

```python
"""Async qBittorrent Web API client for VPN torrent fallback."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class QBittorrentError(Exception):
    """Raised for qBittorrent API errors."""


class QBittorrentClient:
    """Async wrapper around the qBittorrent Web API.

    Assumes qBittorrent runs behind Gluetun VPN container.
    """

    def __init__(self, base_url: str, username: str = "admin", password: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        self._authenticated = False

    async def _login(self) -> None:
        """Authenticate with the qBittorrent Web API."""
        if self._authenticated:
            return
        resp = await self._client.post("/api/v2/auth/login", data={
            "username": self._username,
            "password": self._password,
        })
        if resp.status_code != 200 or resp.text.strip().upper() != "OK.":
            raise QBittorrentError(f"Login failed: {resp.status_code} {resp.text}")
        self._authenticated = True
        logger.info("qBittorrent authenticated")

    async def add_magnet(self, magnet: str, save_path: str, category: str = "automedia") -> None:
        """Add a magnet link for download."""
        await self._login()
        resp = await self._client.post("/api/v2/torrents/add", data={
            "urls": magnet,
            "savepath": save_path,
            "category": category,
        })
        if resp.status_code != 200:
            raise QBittorrentError(f"Add torrent failed: {resp.status_code} {resp.text}")
        logger.info("Added magnet to qBittorrent, save_path=%s", save_path)

    async def get_torrent_info(self, info_hash: str) -> dict | None:
        """Get torrent info by hash. Returns None if not found."""
        await self._login()
        resp = await self._client.get("/api/v2/torrents/info", params={
            "hashes": info_hash.lower(),
        })
        resp.raise_for_status()
        torrents = resp.json()
        return torrents[0] if torrents else None

    async def poll_until_complete(
        self, info_hash: str, timeout: int = 3600, interval: int = 10
    ) -> dict:
        """Poll until torrent reaches 100% or times out."""
        elapsed = 0
        while elapsed < timeout:
            info = await self.get_torrent_info(info_hash)
            if info is None:
                raise QBittorrentError(f"Torrent {info_hash} not found in qBittorrent")

            progress = info.get("progress", 0)
            state = info.get("state", "unknown")
            logger.debug("Torrent %s: %.1f%% state=%s", info_hash[:8], progress * 100, state)

            if progress >= 1.0:
                return info

            if state in ("error", "missingFiles"):
                raise QBittorrentError(f"Torrent entered error state: {state}")

            await asyncio.sleep(interval)
            elapsed += interval

        raise QBittorrentError(f"Torrent {info_hash} timed out after {timeout}s")

    async def delete_torrent(self, info_hash: str, delete_files: bool = False) -> None:
        """Remove a torrent from qBittorrent."""
        await self._login()
        resp = await self._client.post("/api/v2/torrents/delete", data={
            "hashes": info_hash.lower(),
            "deleteFiles": str(delete_files).lower(),
        })
        if resp.status_code != 200:
            logger.warning("Failed to delete torrent %s: %s", info_hash, resp.text)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "QBittorrentClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
```

**Step 2: Commit**

```bash
git add services/shared/qbt_client.py
git commit -m "feat: add qBittorrent async API client"
```

---

### Task 6: SABnzbd Client

**Files:**
- Create: `services/shared/sabnzbd_client.py`

**Step 1: Create sabnzbd_client.py**

```python
"""Async SABnzbd API client for Usenet downloads."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class SABnzbdError(Exception):
    """Raised for SABnzbd API errors."""


class SABnzbdClient:
    """Async wrapper around the SABnzbd API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def _api(self, mode: str, **kwargs) -> dict:
        """Make a SABnzbd API call."""
        params = {"apikey": self._api_key, "mode": mode, "output": "json", **kwargs}
        resp = await self._client.get("/api", params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") is False:
            raise SABnzbdError(f"SABnzbd error: {data.get('error', 'unknown')}")
        return data

    async def add_nzb_url(self, nzb_url: str, category: str = "automedia", name: str = "") -> str:
        """Send an NZB URL to SABnzbd for download. Returns the NZO ID."""
        data = await self._api("addurl", name=nzb_url, cat=category, nzbname=name)
        nzo_ids = data.get("nzo_ids", [])
        if not nzo_ids:
            raise SABnzbdError("SABnzbd returned no NZO IDs after adding URL")
        nzo_id = nzo_ids[0]
        logger.info("Added NZB to SABnzbd, nzo_id=%s", nzo_id)
        return nzo_id

    async def get_slot(self, nzo_id: str) -> dict | None:
        """Get download slot info for a specific NZO ID."""
        # Check active queue
        data = await self._api("queue")
        for slot in data.get("queue", {}).get("slots", []):
            if slot.get("nzo_id") == nzo_id:
                return {**slot, "phase": "downloading"}

        # Check history (completed/failed)
        data = await self._api("history", limit=50)
        for slot in data.get("history", {}).get("slots", []):
            if slot.get("nzo_id") == nzo_id:
                return {**slot, "phase": "completed"}

        return None

    async def poll_until_complete(self, nzo_id: str, timeout: int = 3600, interval: int = 10) -> dict:
        """Poll until NZB download completes or times out."""
        elapsed = 0
        while elapsed < timeout:
            slot = await self.get_slot(nzo_id)
            if slot is None:
                raise SABnzbdError(f"NZO {nzo_id} not found in SABnzbd")

            if slot["phase"] == "completed":
                status = slot.get("status", "")
                if status == "Completed":
                    logger.info("SABnzbd download complete: %s", nzo_id)
                    return slot
                if status == "Failed":
                    raise SABnzbdError(f"SABnzbd download failed: {slot.get('fail_message', 'unknown')}")

            logger.debug("SABnzbd %s: %s%% phase=%s", nzo_id, slot.get("percentage", "?"), slot["phase"])
            await asyncio.sleep(interval)
            elapsed += interval

        raise SABnzbdError(f"SABnzbd download {nzo_id} timed out after {timeout}s")

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SABnzbdClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
```

**Step 2: Commit**

```bash
git add services/shared/sabnzbd_client.py
git commit -m "feat: add SABnzbd async API client"
```

---

### Task 7: Add SABnzbd to Docker Compose

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Add SABnzbd service**

In `docker-compose.yml`, add after the `qbittorrent` service (after line 216):

```yaml
  sabnzbd:
    image: lscr.io/linuxserver/sabnzbd:latest
    container_name: automedia-sabnzbd
    restart: unless-stopped
    environment:
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
      - TZ=${TZ:-America/New_York}
    volumes:
      - ${CONFIG_PATH:-./config}/sabnzbd:/config
      - ${DOWNLOADS_PATH:-./data/downloads}:/downloads
    profiles:
      - usenet
    networks:
      - internal
```

**Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add SABnzbd to docker-compose (usenet profile)"
```

---

### Task 8: Rewrite Worker Acquisition — Multi-Method with Candidate Fallback

This is the core task. The worker's `acquire()` becomes `acquire_with_fallback()` which tries multiple candidates and multiple methods.

**Files:**
- Modify: `services/agent-worker/worker.py:156-509`

**Step 1: Add imports**

At top of worker.py, add:

```python
from shared.qbt_client import QBittorrentClient
from shared.sabnzbd_client import SABnzbdClient
from shared.redis_client import set_download_progress, clear_download_progress
```

**Step 2: Replace the SELECTED and ACQUIRE sections of process_job**

Replace lines 233-275 (from `# 4. SELECT` through `await acquire(job, best, prefs_dict)`) with:

```python
    # ------------------------------------------------------------------
    # 4. ACQUIRE with fallback -- try top candidates
    # ------------------------------------------------------------------
    scored = [(c, score_candidate(c, prefs_dict if job.media_type == "movie" else scoring_prefs)) for c in candidates]
    valid = sorted([(c, s) for c, s in scored if s > 0], key=lambda x: (-x[1], x[0].size_gb))

    if not valid:
        await transition(
            job, JobState.FAILED,
            f"No valid candidates found (searched {len(raw_results)} results, {len(candidates)} after blacklist)",
        )
        return

    await acquire_with_fallback(job, valid, prefs_dict, year)
```

**Step 3: Write acquire_with_fallback**

Replace the old `acquire()` function (lines 283-303) with:

```python
async def acquire_with_fallback(
    job: Job,
    scored_candidates: list[tuple[ParsedRelease, int]],
    prefs: dict,
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
```

**Step 4: Rewrite acquire() for multi-method**

Replace the existing `acquire()` function with:

```python
async def acquire(
    job: Job,
    candidate: ParsedRelease,
    prefs: dict,
) -> None:
    """Try acquisition methods in priority order. Raises on all-method failure."""
    config = get_config()
    errors: list[str] = []

    # 1. Real-Debrid (if enabled and candidate has magnet/hash)
    if config.rd_enabled and config.rd_api_token:
        try:
            if job.acquisition_mode == "stream":
                await acquire_via_rd_stream(job, candidate)
            else:
                await acquire_via_rd(job, candidate)
            # Record which method succeeded
            await _set_acquisition_method(job, "rd")
            return
        except Exception as exc:
            msg = f"RD: {diagnose_failure(exc, candidate)}"
            errors.append(msg)
            await transition(job, JobState.ACQUIRING, msg)

    # 2. Usenet (if enabled and candidate has NZB download URL, not a magnet)
    if config.usenet_enabled and config.sabnzbd_api_key:
        nzb_url = candidate.magnet_link
        if nzb_url and not nzb_url.startswith("magnet:"):
            try:
                await acquire_via_usenet(job, candidate)
                await _set_acquisition_method(job, "usenet")
                return
            except Exception as exc:
                msg = f"Usenet: {diagnose_failure(exc, candidate)}"
                errors.append(msg)
                await transition(job, JobState.ACQUIRING, msg)

    # 3. VPN Torrent (if enabled)
    if config.vpn_enabled and config.qbt_password:
        try:
            await acquire_via_torrent(job, candidate)
            await _set_acquisition_method(job, "torrent")
            return
        except Exception as exc:
            msg = f"Torrent: {diagnose_failure(exc, candidate)}"
            errors.append(msg)
            await transition(job, JobState.ACQUIRING, msg)

    # All methods failed for this candidate
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
```

**Step 5: Add streaming mode acquisition**

Add after `acquire_via_rd`:

```python
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

        # Persist RD torrent ID
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

        # Unrestrict all links to get direct streaming URLs
        streaming_urls = []
        for raw_link in links:
            url = await rd.unrestrict_link(raw_link)
            streaming_urls.append(url)

        # Persist streaming URLs on the job
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
```

**Step 6: Add Usenet acquisition**

```python
async def acquire_via_usenet(job: Job, candidate: ParsedRelease) -> None:
    """Download via SABnzbd Usenet client."""
    config = get_config()

    async with SABnzbdClient(config.sabnzbd_url, config.sabnzbd_api_key) as sab:
        await transition(job, JobState.ACQUIRING, "Sending NZB to SABnzbd")

        nzo_id = await sab.add_nzb_url(
            candidate.magnet_link,  # For Usenet results, this is the NZB download URL
            category="automedia",
            name=candidate.title,
        )

        await transition(job, JobState.ACQUIRING, f"SABnzbd downloading (nzo={nzo_id})")
        slot = await sab.poll_until_complete(nzo_id, timeout=3600)

        # SABnzbd puts completed downloads in a category folder
        storage_path = slot.get("storage", "")
        if not storage_path:
            raise RuntimeError("SABnzbd completed but reported no storage path")

    staging_dir = Path(storage_path)
    await transition(job, JobState.IMPORTING, "Importing Usenet download to media library")
    await import_files(job, staging_dir)
```

**Step 7: Add VPN torrent acquisition**

```python
async def check_vpn_health() -> bool:
    """Check if Gluetun VPN is healthy."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://gluetun:9999")
            return resp.status_code == 200
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

        # qBittorrent needs a moment to register the torrent
        await asyncio.sleep(3)

        info_hash = candidate.info_hash
        if not info_hash:
            # Extract from magnet URI
            import re
            match = re.search(r'btih:([a-fA-F0-9]+)', magnet)
            if match:
                info_hash = match.group(1)
            else:
                raise RuntimeError("Cannot determine info_hash for torrent polling")

        await transition(job, JobState.ACQUIRING, "Waiting for qBittorrent download (VPN)")
        info = await qbt.poll_until_complete(info_hash, timeout=3600)

        # Clean up torrent from qBit (keep files)
        await qbt.delete_torrent(info_hash, delete_files=False)

    staging_dir = Path(save_path)
    await transition(job, JobState.IMPORTING, "Importing torrent download to media library")
    await import_files(job, staging_dir)
```

**Step 8: Wire progress tracking into acquire_via_rd**

In the existing `acquire_via_rd`, modify the download loop (around line 410-432) to use the progress callback:

```python
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
            async def _on_progress(downloaded: int, total: int, _job_id=str(job.id), _fname=filename) -> None:
                pct = int(downloaded / total * 100) if total > 0 else 0
                if pct >= last_pct[0] + 5:  # Report every 5%
                    last_pct[0] = pct
                    await set_download_progress(_job_id, pct, f"Downloading {_fname} ({idx+1}/{len(links)})")

            try:
                await rd.download_file(download_url, dest, on_progress=_on_progress)
                logger.info("Downloaded %s -> %s", filename, dest)
            except Exception as exc:
                logger.warning("Failed to download %s: %s", download_url, exc)
                continue

        await clear_download_progress(str(job.id))
```

Wait — the `on_progress` callback in `rd_client.download_file` is synchronous (no await). Since we need to call `set_download_progress` which is async, we need to adjust. Make the progress callback synchronous and batch the Redis update:

Actually, let's keep it simpler. Make the callback in rd_client accept an async callable too:

In `rd_client.py`, change the download loop:

```python
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 256):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total > 0:
                            result = on_progress(downloaded, total)
                            if asyncio.iscoroutine(result):
                                await result
```

And in worker.py, rate-limit the progress reports:

```python
            last_pct = [0]

            async def _on_progress(downloaded: int, total: int) -> None:
                pct = int(downloaded / total * 100) if total > 0 else 0
                if pct >= last_pct[0] + 5:
                    last_pct[0] = pct
                    await set_download_progress(
                        str(job.id), pct,
                        f"Downloading {filename} ({idx+1}/{len(links)})"
                    )

            try:
                await rd.download_file(download_url, dest, on_progress=_on_progress)
```

**Step 9: Commit**

```bash
git add services/agent-worker/worker.py
git commit -m "feat: multi-method acquisition with candidate fallback, streaming, Usenet, VPN torrent"
```

---

### Task 9: Prowlarr Indexer Setup Script

**Files:**
- Create: `scripts/setup-indexers.sh`

**Step 1: Write the script**

```bash
#!/usr/bin/env bash
# setup-indexers.sh — Add all available public torrent indexers to Prowlarr
# Usage: ./scripts/setup-indexers.sh
# Idempotent: skips indexers that already exist.

set -euo pipefail

PROWLARR_URL="${PROWLARR_URL:-http://localhost:9696}"

# Try to read API key from config file first, then env
if [ -z "${PROWLARR_API_KEY:-}" ]; then
    CONFIG_FILE="${CONFIG_PATH:-./config}/prowlarr/config.xml"
    if [ -f "$CONFIG_FILE" ]; then
        PROWLARR_API_KEY=$(grep -oP '(?<=<ApiKey>)[^<]+' "$CONFIG_FILE" 2>/dev/null || true)
    fi
fi

if [ -z "${PROWLARR_API_KEY:-}" ]; then
    echo "ERROR: PROWLARR_API_KEY not set and could not read from config.xml"
    exit 1
fi

HEADERS=(-H "X-Api-Key: $PROWLARR_API_KEY" -H "Content-Type: application/json")

echo "=== Prowlarr Indexer Setup ==="
echo "URL: $PROWLARR_URL"
echo ""

# ── Step 1: Get existing indexers ──
echo "Checking existing indexers..."
EXISTING=$(curl -sf "$PROWLARR_URL/api/v1/indexer" "${HEADERS[@]}")
EXISTING_NAMES=$(echo "$EXISTING" | python3 -c "
import sys, json
for idx in json.load(sys.stdin):
    print(idx.get('definitionName', '').lower())
" 2>/dev/null || true)
echo "Found $(echo "$EXISTING_NAMES" | grep -c . || echo 0) existing indexers"
echo ""

# ── Step 2: Get available schemas ──
echo "Fetching available indexer schemas..."
SCHEMAS=$(curl -sf "$PROWLARR_URL/api/v1/indexer/schema" "${HEADERS[@]}")

# Filter to public torrent indexers and extract names
PUBLIC_INDEXERS=$(echo "$SCHEMAS" | python3 -c "
import sys, json
schemas = json.load(sys.stdin)
seen = set()
for s in schemas:
    proto = s.get('protocol', '')
    privacy = s.get('privacy', '')
    defn = s.get('definitionName', '')
    if proto == 'torrent' and privacy == 'public' and defn and defn not in seen:
        seen.add(defn)
        impl = s.get('implementation', '')
        contract = s.get('configContract', '')
        print(f'{defn}|{impl}|{contract}')
" 2>/dev/null | sort)

TOTAL=$(echo "$PUBLIC_INDEXERS" | grep -c . || echo 0)
echo "Found $TOTAL public torrent indexer definitions"
echo ""

# ── Step 3: Add missing indexers ──
ADDED=0
SKIPPED=0
FAILED=0

while IFS='|' read -r DEF_NAME IMPL CONTRACT; do
    [ -z "$DEF_NAME" ] && continue

    # Check if already exists
    if echo "$EXISTING_NAMES" | grep -qi "^${DEF_NAME}$"; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    echo -n "  Adding: $DEF_NAME ... "

    PAYLOAD=$(python3 -c "
import json
print(json.dumps({
    'name': '$DEF_NAME',
    'definitionName': '$DEF_NAME',
    'implementation': '$IMPL',
    'configContract': '$CONTRACT',
    'enable': True,
    'appProfileId': 1,
    'protocol': 'torrent',
    'privacy': 'public',
    'fields': [],
    'tags': []
}))
")

    RESULT=$(curl -sf -w "%{http_code}" -o /tmp/prowlarr_add.json \
        -X POST "$PROWLARR_URL/api/v1/indexer" \
        "${HEADERS[@]}" \
        -d "$PAYLOAD" 2>/dev/null || echo "000")

    if [ "$RESULT" = "201" ] || [ "$RESULT" = "200" ]; then
        echo "OK"
        ADDED=$((ADDED + 1))
    else
        MSG=$(cat /tmp/prowlarr_add.json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('message', d.get('errorMessage', str(d)))[:80])
except:
    print('unknown error')
" 2>/dev/null || echo "HTTP $RESULT")
        echo "FAILED ($MSG)"
        FAILED=$((FAILED + 1))
    fi
done <<< "$PUBLIC_INDEXERS"

echo ""
echo "=== Results ==="
echo "  Added:   $ADDED"
echo "  Skipped: $SKIPPED (already exist)"
echo "  Failed:  $FAILED"
echo ""

# ── Step 4: Configure FlareSolverr proxy ──
echo "Checking FlareSolverr proxy..."
PROXIES=$(curl -sf "$PROWLARR_URL/api/v1/indexerProxy" "${HEADERS[@]}" 2>/dev/null || echo "[]")
HAS_FLARE=$(echo "$PROXIES" | python3 -c "
import sys, json
proxies = json.load(sys.stdin)
print('yes' if any(p.get('implementation') == 'FlareSolverr' for p in proxies) else 'no')
" 2>/dev/null || echo "no")

if [ "$HAS_FLARE" = "no" ]; then
    echo "  Adding FlareSolverr proxy..."
    curl -sf -X POST "$PROWLARR_URL/api/v1/indexerProxy" \
        "${HEADERS[@]}" \
        -d '{
            "name": "FlareSolverr",
            "implementation": "FlareSolverr",
            "configContract": "FlareSolverrSettings",
            "fields": [
                {"name": "host", "value": "http://flaresolverr:8191"},
                {"name": "requestTimeout", "value": 60}
            ],
            "tags": []
        }' > /dev/null 2>&1 && echo "  FlareSolverr proxy added" || echo "  Failed to add FlareSolverr proxy"
else
    echo "  FlareSolverr proxy already configured"
fi
echo ""

# ── Step 5: Sync to Sonarr/Radarr ──
echo "Syncing indexers to Sonarr/Radarr..."
curl -sf -X POST "$PROWLARR_URL/api/v1/indexer/action/SyncAll" \
    "${HEADERS[@]}" > /dev/null 2>&1 && echo "  Sync triggered" || echo "  Sync failed (may not be connected)"
echo ""

# ── Step 6: Test search ──
echo "Running test search for 'The Matrix'..."
RESULTS=$(curl -sf "$PROWLARR_URL/api/v1/search?query=The+Matrix&type=search" \
    "${HEADERS[@]}" 2>/dev/null || echo "[]")
echo "$RESULTS" | python3 -c "
import sys, json
results = json.load(sys.stdin)
print(f'  Total results: {len(results)}')
# Count by indexer
by_indexer = {}
for r in results:
    idx = r.get('indexer', 'unknown')
    by_indexer[idx] = by_indexer.get(idx, 0) + 1
for idx, count in sorted(by_indexer.items(), key=lambda x: -x[1])[:15]:
    print(f'    {idx:30s} {count:5d} results')
" 2>/dev/null || echo "  Could not parse search results"

echo ""
echo "=== Done ==="
```

**Step 2: Make executable**

```bash
chmod +x scripts/setup-indexers.sh
```

**Step 3: Commit**

```bash
git add scripts/setup-indexers.sh
git commit -m "feat: add reusable Prowlarr public indexer setup script"
```

---

### Task 10: Run Indexer Script + Verify

**Step 1: Run the setup script**

```bash
cd /home/shawn/Automated-ai-media-center-/invisible-arr/edge-node
./scripts/setup-indexers.sh
```

**Step 2: Verify results**

Check that search returns results from multiple indexers. If some indexers failed, check the Prowlarr logs:

```bash
docker compose logs prowlarr --tail=50
```

---

### Task 11: Rebuild and Test

**Step 1: Run the migration**

```bash
docker compose exec agent-api alembic upgrade head
```

**Step 2: Rebuild worker with new code**

```bash
docker compose build agent-worker agent-api
docker compose up -d agent-worker agent-api
```

**Step 3: Test a request**

```bash
API_KEY=$(docker compose exec -T postgres psql -U invisiblearr -d invisiblearr -t -c "SELECT api_key FROM users LIMIT 1;" 2>/dev/null | tr -d ' \n')

curl -s -X POST http://localhost:8880/v1/request \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"query": "The Matrix", "media_type": "movie"}' | python3 -m json.tool
```

**Step 4: Check job progress**

```bash
# Get latest job ID
JOB_ID=$(curl -s http://localhost:8880/v1/jobs -H "X-Api-Key: $API_KEY" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# Watch progress
curl -s "http://localhost:8880/v1/jobs/$JOB_ID/progress" -H "X-Api-Key: $API_KEY" | python3 -m json.tool

# Full job detail
curl -s "http://localhost:8880/v1/jobs/$JOB_ID" -H "X-Api-Key: $API_KEY" | python3 -m json.tool
```

**Step 5: Verify new fields in response**

The job response should now include `acquisition_method` and `streaming_urls` fields.

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: backend download pipeline — indexers, Usenet, streaming, VPN fallback, progress tracking"
```

---

## Summary

| Task | Description | Estimated complexity |
|------|-------------|---------------------|
| 1 | Config vars | Low |
| 2 | DB migration + model fields | Low |
| 3 | Download progress tracking | Medium |
| 4 | Error diagnostics | Low |
| 5 | qBittorrent client | Medium |
| 6 | SABnzbd client | Medium |
| 7 | SABnzbd in docker-compose | Low |
| 8 | Worker rewrite (core) | High |
| 9 | Prowlarr indexer script | Medium |
| 10 | Run indexer script | Low |
| 11 | Rebuild + integration test | Medium |

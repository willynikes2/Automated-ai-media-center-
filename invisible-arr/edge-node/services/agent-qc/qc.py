"""Quality-control validation for downloaded media files.

Uses ffprobe to inspect container metadata and enforces minimum thresholds
for stream presence, duration, file size, and resolution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
MIN_DURATION_SECONDS: float = 300.0    # 5 minutes -- catches sample clips
MIN_FILE_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB -- catches fakes
MIN_WIDTH: int = 320
MIN_HEIGHT: int = 240
FFPROBE_TIMEOUT_SECONDS: int = 60


async def validate_file(file_path: str) -> tuple[bool, str]:
    """Run ffprobe against *file_path* and validate the media.

    Returns
    -------
    tuple[bool, str]
        ``(True, "Valid: WxH, Ns, NMB")`` on success, or
        ``(False, "reason")`` on failure.
    """
    # ------------------------------------------------------------------
    # 1. Basic existence / size check
    # ------------------------------------------------------------------
    if not os.path.isfile(file_path):
        return False, f"File not found: {file_path}"

    file_size_bytes = os.path.getsize(file_path)
    if file_size_bytes < MIN_FILE_SIZE_BYTES:
        size_mb = file_size_bytes / (1024 * 1024)
        return (
            False,
            f"File too small: {size_mb:.1f}MB (minimum {MIN_FILE_SIZE_BYTES // (1024 * 1024)}MB)",
        )

    # ------------------------------------------------------------------
    # 2. Run ffprobe
    # ------------------------------------------------------------------
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "--",
        file_path,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.error("ffprobe timed out after %ds for %s", FFPROBE_TIMEOUT_SECONDS, file_path)
        return False, f"ffprobe timed out after {FFPROBE_TIMEOUT_SECONDS}s"
    except Exception as exc:
        logger.exception("ffprobe execution failed for %s", file_path)
        return False, f"ffprobe error: {exc}"

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        return False, f"ffprobe returned exit code {proc.returncode}: {err_msg}"

    try:
        probe: dict = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return False, f"ffprobe output is not valid JSON: {exc}"

    # ------------------------------------------------------------------
    # 3. Stream presence checks
    # ------------------------------------------------------------------
    streams: list[dict] = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if not video_streams:
        return False, "No video stream found"

    if not audio_streams:
        return False, "No audio stream found"

    # ------------------------------------------------------------------
    # 4. Duration check (from format or first video stream)
    # ------------------------------------------------------------------
    fmt: dict = probe.get("format", {})
    duration_str: str | None = fmt.get("duration") or video_streams[0].get("duration")

    if duration_str is None:
        return False, "Unable to determine duration"

    try:
        duration = float(duration_str)
    except (ValueError, TypeError):
        return False, f"Invalid duration value: {duration_str}"

    if duration < MIN_DURATION_SECONDS:
        return (
            False,
            f"Duration too short: {duration:.0f}s (minimum {MIN_DURATION_SECONDS:.0f}s)",
        )

    # ------------------------------------------------------------------
    # 5. Resolution check
    # ------------------------------------------------------------------
    primary_video = video_streams[0]
    width: int | None = primary_video.get("width")
    height: int | None = primary_video.get("height")

    if width is None or height is None:
        return False, "Unable to determine resolution"

    try:
        width = int(width)
        height = int(height)
    except (ValueError, TypeError):
        return False, f"Invalid resolution values: {width}x{height}"

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return (
            False,
            f"Resolution too low: {width}x{height} (minimum {MIN_WIDTH}x{MIN_HEIGHT})",
        )

    # ------------------------------------------------------------------
    # 6. All checks passed
    # ------------------------------------------------------------------
    size_mb = file_size_bytes / (1024 * 1024)
    summary = f"Valid: {width}x{height}, {duration:.0f}s, {size_mb:.0f}MB"
    logger.info("QC PASS for %s -- %s", file_path, summary)
    return True, summary

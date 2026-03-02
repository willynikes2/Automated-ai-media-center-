"""Deterministic release scoring -- no LLM required.

Parses structured metadata from release titles and scores candidates
against user quality preferences.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedRelease:
    """Structured metadata extracted from a release title."""

    title: str
    resolution: int = 0        # 480, 720, 1080, 2160
    source: str = "unknown"    # BluRay, WEB-DL, WEBRip, HDTV, etc.
    codec: str = "unknown"     # x265, x264, AV1, etc.
    audio: str = "unknown"     # DTS-HD, TrueHD, Atmos, AAC, etc.
    size_gb: float = 0.0
    seeders: int = 0
    info_hash: str = ""
    magnet_link: str = ""
    indexer: str = ""
    banned: bool = False
    ban_reason: str = ""


def parse_release_title(title: str) -> ParsedRelease:
    """Extract structured metadata from a release title using regex."""
    p = ParsedRelease(title=title)

    # Resolution
    m = re.search(r'(2160|1080|720|480)[pi]?', title, re.I)
    if m:
        p.resolution = int(m.group(1))

    # Source
    source_map = [
        (r'REMUX', 'REMUX'), (r'Blu[\-\.]?Ray', 'BluRay'),
        (r'WEB[\-\.]?DL', 'WEB-DL'), (r'WEB[\-\.]?Rip', 'WEBRip'),
        (r'HDRip', 'HDRip'), (r'BDRip', 'BDRip'), (r'HDTV', 'HDTV'),
        (r'DVDRip', 'DVDRip'), (r'WEB', 'WEB'),
    ]
    for pattern, label in source_map:
        if re.search(pattern, title, re.I):
            p.source = label
            break

    # Codec
    codec_map = [
        (r'[xh][\.\-]?265|HEVC', 'x265'), (r'[xh][\.\-]?264|AVC', 'x264'),
        (r'AV1', 'AV1'), (r'VP9', 'VP9'), (r'MPEG[\-]?2', 'MPEG2'),
    ]
    for pattern, label in codec_map:
        if re.search(pattern, title, re.I):
            p.codec = label
            break

    # Audio
    audio_map = [
        (r'DTS[\-\.]?HD(?:[\.\-]?MA)?', 'DTS-HD'), (r'TrueHD', 'TrueHD'),
        (r'Atmos', 'Atmos'), (r'DTS', 'DTS'), (r'DD[\+P]?5[\.\-]1', 'DD5.1'),
        (r'AAC', 'AAC'), (r'FLAC', 'FLAC'), (r'EAC3|E-AC-3', 'EAC3'),
        (r'AC3|AC-3', 'AC3'),
    ]
    for pattern, label in audio_map:
        if re.search(pattern, title, re.I):
            p.audio = label
            break

    # Banned tags (hard reject)
    banned_tags = [r'\bCAM\b', r'\bTS\b', r'\bHDCAM\b', r'\bTELESYNC\b', r'\bHDTS\b']
    for bt in banned_tags:
        if re.search(bt, title, re.I):
            p.banned = True
            p.ban_reason = f"Banned tag: {bt}"
            break

    return p


def score_candidate(parsed: ParsedRelease, prefs: dict) -> int:
    """Score a release candidate.  Higher is better.  Returns -1 if rejected by policy."""
    if parsed.banned:
        return -1

    # Hard policy filters
    max_res = prefs.get("max_resolution", 1080)
    if parsed.resolution > max_res:
        if parsed.resolution == 2160 and not prefs.get("allow_4k", False):
            return -1

    max_size = prefs.get("max_movie_size_gb", 15.0)  # caller passes correct field
    if parsed.size_gb > 0 and parsed.size_gb > max_size:
        return -1

    # Resolution score
    res_scores = {2160: 100, 1080: 80, 720: 50, 480: 20}
    score = res_scores.get(parsed.resolution, 10)

    # Source score
    src_scores = {
        "REMUX": 100, "BluRay": 90, "WEB-DL": 80, "WEB": 75,
        "WEBRip": 60, "BDRip": 55, "HDRip": 50, "HDTV": 40,
        "DVDRip": 20, "unknown": 10,
    }
    score += src_scores.get(parsed.source, 10)

    # Codec score
    codec_scores = {
        "AV1": 85, "x265": 80, "x264": 60, "VP9": 50,
        "MPEG2": 20, "unknown": 30,
    }
    score += codec_scores.get(parsed.codec, 30)

    # Seeder bonus (cap at 20)
    score += min(parsed.seeders // 10, 20)

    return score


def select_best_candidate(
    candidates: list[ParsedRelease], prefs: dict
) -> ParsedRelease | None:
    """Pick the best candidate by score.  Ties broken by smallest size."""
    scored = [(c, score_candidate(c, prefs)) for c in candidates]
    valid = [(c, s) for c, s in scored if s > 0]
    if not valid:
        return None
    valid.sort(key=lambda x: (-x[1], x[0].size_gb))
    return valid[0][0]

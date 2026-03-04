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
    protocol: str = "torrent"  # torrent | usenet
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

    # TRaSH unwanted: LQ release groups
    lq_groups = [
        r'\bYIFY\b', r'\bYTS\b', r'\bEVO\b', r'\bAXXO\b', r'\bKOOKS\b',
        r'\bRAARBG\b', r'\bMeGusta\b', r'\bHive[\-\.]?CM8\b',
        r'\bSEZON\b', r'\bTiGER\b', r'\bTROPIC\b', r'\bPSA\b',
    ]
    if not p.banned:
        for lg in lq_groups:
            if re.search(lg, title, re.I):
                p.banned = True
                p.ban_reason = f"LQ release group: {lg}"
                break

    # TRaSH unwanted: BR-DISK / 3D
    if not p.banned:
        if re.search(r'\b(BD25|BD50|BDMV|COMPLETE[\.\-\s]?BLURAY)\b', title, re.I):
            p.banned = True
            p.ban_reason = "BR-DISK (full disc)"
        elif re.search(r'\b3D\b', title, re.I):
            p.banned = True
            p.ban_reason = "3D release"

    return p


def _normalize_title(title: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from a title."""
    return set(re.findall(r'[a-z0-9]+', title.lower()))


def title_matches(release_title: str, canonical_title: str, year: int = 0) -> bool:
    """Check if a release title is relevant to the requested media.

    Returns True if the release title contains all significant words from
    the canonical title.  Rejects obvious mismatches like "Scream VI" when
    requesting "Scream 7", or "Poseidon" when requesting "Pose".
    """
    # Normalize both titles to lowercase token sets
    release_tokens = _normalize_title(release_title)
    canonical_tokens = _normalize_title(canonical_title)

    # Remove very short/common tokens that cause false matches
    noise = {'the', 'a', 'an', 'and', 'of', 'in', 'on', 'at', 'to', 'for', 'is', 'it', 'by'}
    canonical_significant = canonical_tokens - noise

    if not canonical_significant:
        return True  # safety: don't filter if no significant tokens

    # All significant canonical tokens must appear in the release title
    matched = canonical_significant & release_tokens
    if len(matched) < len(canonical_significant):
        return False

    # Year check: if the release contains a different 4-digit year, reject
    if year > 0:
        release_years = {int(t) for t in release_tokens if t.isdigit() and len(t) == 4 and 1900 <= int(t) <= 2099}
        if release_years and year not in release_years:
            return False

    return True


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

    # TRaSH: Reject REMUX for HD content (too large for non-4K)
    if parsed.source == "REMUX" and parsed.resolution <= 1080:
        return -1

    # TRaSH: Reject AV1 (poor playback compatibility)
    if parsed.codec == "AV1":
        return -1

    # Resolution score
    res_scores = {2160: 100, 1080: 80, 720: 50, 480: 20}
    score = res_scores.get(parsed.resolution, 10)

    # Source score (REMUX only reachable here for 4K)
    src_scores = {
        "REMUX": 100, "BluRay": 90, "WEB-DL": 80, "WEB": 75,
        "WEBRip": 60, "BDRip": 55, "HDRip": 50, "HDTV": 40,
        "DVDRip": 20, "unknown": 10,
    }
    score += src_scores.get(parsed.source, 10)

    # Codec score — TRaSH x265 HD penalty (x265 at 1080p has limited benefit)
    if parsed.codec == "x265" and parsed.resolution <= 1080:
        score += 40  # reduced from 80
    else:
        codec_scores = {
            "x265": 80, "x264": 60, "VP9": 50,
            "MPEG2": 20, "unknown": 30,
        }
        score += codec_scores.get(parsed.codec, 30)

    # Seeder bonus (cap at 20)
    score += min(parsed.seeders // 10, 20)

    # Protocol preference: usenet is faster than torrent
    if parsed.protocol == "usenet":
        score += 30

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

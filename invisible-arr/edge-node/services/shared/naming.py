"""Media file naming and path generation.

Produces Jellyfin/Plex-compatible folder structures:
- Movies: ``Title (Year)/Title (Year).ext``
- TV: ``Show Title (Year)/Season 01/Show Title (Year) - S01E01.ext``
"""

import re
from pathlib import Path

# Patterns to extract season/episode from filenames
_SE_PATTERNS: list[re.Pattern[str]] = [
    # S01E01, S01E01E02 (multi-ep → returns first episode)
    re.compile(r'[Ss](\d{1,2})\s*[Ee](\d{1,3})'),
    # 1x05
    re.compile(r'(\d{1,2})x(\d{2,3})'),
]


def sanitize(name: str) -> str:
    """Remove filesystem-unsafe characters and path traversal sequences."""
    name = name.replace('..', '')
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


def validate_path(dest: Path, root: Path) -> Path:
    """Resolve *dest* and ensure it lives under *root*.

    Raises
    ------
    ValueError
        If the resolved *dest* escapes the *root* directory.
    """
    resolved_dest = dest.resolve()
    resolved_root = root.resolve()
    try:
        resolved_dest.relative_to(resolved_root)
    except ValueError:
        raise ValueError(
            f"Path {resolved_dest} is outside root {resolved_root}"
        ) from None
    return resolved_dest


def extract_episode_info(filename: str) -> tuple[int, int] | None:
    """Extract (season, episode) from a filename.

    Handles patterns like ``S01E05``, ``s02e10``, ``1x05``.
    Returns ``None`` if no pattern matches.
    """
    for pat in _SE_PATTERNS:
        m = pat.search(filename)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def movie_path(title: str, year: int, ext: str) -> Path:
    """Return the relative path for a movie file.

    Example::

        >>> movie_path("The Matrix", 1999, ".mkv")
        PosixPath('The Matrix (1999)/The Matrix (1999).mkv')
    """
    clean = sanitize(title)
    folder = f"{clean} ({year})"
    return Path(folder) / f"{clean} ({year}){ext}"


def tv_path(show: str, season: int, episode: int, ext: str,
            year: int | None = None) -> Path:
    """Return the relative path for a TV episode file.

    Examples::

        >>> tv_path("Breaking Bad", 1, 1, ".mkv", year=2008)
        PosixPath('Breaking Bad (2008)/Season 01/Breaking Bad (2008) - S01E01.mkv')

        >>> tv_path("Breaking Bad", 1, 1, ".mkv")
        PosixPath('Breaking Bad/Season 01/Breaking Bad - S01E01.mkv')
    """
    clean = sanitize(show)
    label = f"{clean} ({year})" if year else clean
    return (
        Path(label)
        / f"Season {season:02d}"
        / f"{label} - S{season:02d}E{episode:02d}{ext}"
    )
